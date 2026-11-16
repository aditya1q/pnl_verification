"""Daily broker net position report: the day's P&L input and official Close Rates.

The broker's daily "Net Position" report (e.g. NETPOSS02112026_FO_B-117.xls, or
the .txt "Clientwise Net Position") lists, for every contract the account
traded that day, the day's Buy/Sale quantity and value and the exchange Close
Rate. That is everything the broker-method P&L needs: one report per trading
day (after the Carry Forward) is the whole input of the reports.

Importing the report for a day:

- checks that its rows add up to its own Buy/Sale quantity and value totals and
  that no contract appears twice,
- refuses a day on or before the Carry Forward date (the C/F already covers it),
- replaces that day's rows in ``net_positions`` (every column of the report is
  kept), so a day is never counted twice,
- stores each contract's Close Rate in ``market_prices`` for that date with
  ``source = "BROKER_CLOSE"``; open positions are marked to it,
- lists weekdays since the previous loaded day that have no report (a missing
  report, or a holiday).

Re-importing the same day replaces it, so it is idempotent.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from pymongo import ASCENDING

from .carry_forward import (MONTHS, CarryForwardError, CarryForwardStore, _strike, _symbol, exchange_for,
                            parse_net_position)

SOURCE = "BROKER_CLOSE"
# Sort keys for the day view: report order is underlying, option type, expiry, strike.
ROW_SORT_FIELDS = {
    "contract": ["underlying", "option_type", "expiry_date", "strike"],
    "buy_qty": ["buy_qty"], "buy_value": ["buy_value"], "sell_qty": ["sell_qty"], "sell_value": ["sell_value"],
    "net_qty": ["net_qty"], "net_value": ["net_value"], "close_rate": ["close_rate"], "mtm": ["mtm"],
    "line": ["source_line"],
}
DATE_RANGE = re.compile(r"From\s*:\s*(\d\d)-(\d\d)-(\d{4})\s*TO\s*:?\s*(\d\d)-(\d\d)-(\d{4})", re.IGNORECASE)
VALUE_TOLERANCE = Decimal("0.05")


class ClosingRateError(ValueError):
    pass


def _dmy(day, month, year):
    return f"{year}-{month}-{day}"


def _decimal(value):
    text = str(value).strip()
    return Decimal(text) if text else Decimal(0)


def parse_xls_report(content):
    """Rows of the broker's .xls Net Position report (one trading day)."""
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise ClosingRateError("Reading .xls needs the 'xlrd' package (pip install xlrd).") from exc
    try:
        sheet = xlrd.open_workbook(file_contents=content, logfile=_Silent()).sheet_by_index(0)
    except Exception as exc:
        raise ClosingRateError(f"Could not open the .xls report: {exc}") from exc

    return _parse_grid([[str(v).strip() for v in sheet.row_values(r)] for r in range(sheet.nrows)])


def parse_csv_report(content):
    """Rows of the broker's .csv Net Position report (same columns as the .xls)."""
    import csv
    import io
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    return _parse_grid([[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))])


def _parse_grid(lines):
    """Broker Net Position report as a grid of cells (.xls sheet or .csv)."""
    as_of = header = None
    client = None
    for cells in lines:
        joined = " ".join(c for c in cells if c)
        found = DATE_RANGE.search(joined)
        if found and as_of is None:
            start, end = _dmy(*found.groups()[:3]), _dmy(*found.groups()[3:])
            if start != end:
                raise ClosingRateError(f"The report covers {start} to {end}; upload a single-day report.")
            as_of = start
        if joined.startswith("Client:") and client is None:
            client = " / ".join(joined.split(":", 1)[1].split())
        if "Clos Rate" in cells and "Contract" in cells:
            header = cells
    if not as_of:
        raise ClosingRateError("Report date ('Date Range From ... TO ...') not found.")
    if not header:
        raise ClosingRateError("Column header row (Contract ... Clos Rate) not found.")
    col = {name: header.index(name) for name in header if name}
    needed = ("Contract", "Symbol", "Expiry Date", "StrikePrice", "Opt Type", "Buy Qty", "Buy Value",
              "Sale Qty", "Sale Value", "Clos Rate")
    missing = [name for name in needed if name not in col]
    if missing:
        raise ClosingRateError(f"Report columns missing: {', '.join(missing)}")

    rows, totals = [], None
    for number, cells in enumerate(lines, start=1):
        first = cells[0] if cells else ""
        if first == "*" and cells[col["Contract"]] in ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"):
            # 03-11-2026, or 3/11/2026 after Excel re-saves the file (always day first).
            try:
                day, month, year = re.split(r"[-/.]", cells[col["Expiry Date"]].strip())
                expiry = f"{int(day):02d} {MONTHS[int(month) - 1]} {int(year)}"
            except (ValueError, IndexError) as exc:
                raise ClosingRateError(f"line {number}: unreadable Expiry Date {cells[col['Expiry Date']]!r}") from exc
            rows.append({
                "line": number,
                "instrument_name": cells[col["Contract"]],
                "underlying": cells[col["Symbol"]],
                "expiry": expiry,
                "strike": _strike(cells[col["StrikePrice"]] if cells[col["Opt Type"]] else ""),
                "option_type": cells[col["Opt Type"]] or "FX",
                "buy_qty": int(_decimal(cells[col["Buy Qty"]])), "buy_value": _decimal(cells[col["Buy Value"]]),
                "sell_qty": int(_decimal(cells[col["Sale Qty"]])), "sell_value": _decimal(cells[col["Sale Value"]]),
                "close_rate": _decimal(cells[col["Clos Rate"]]),
            })
            row = rows[-1]
            # Keep every other column of the report as it is (stored with the row).
            optional = {"Net Qty": ("net_qty", int), "Net Value": ("net_value", None), "Avg Rate": ("avg_rate", None),
                        "MTM": ("mtm", None), "Exchange": ("report_exchange", str), "Group": ("group", str)}
            for column, (field, kind) in optional.items():
                if column in col and col[column] < len(cells):
                    raw = cells[col[column]]
                    row[field] = raw if kind is str else (int(_decimal(raw)) if kind is int else _decimal(raw))
            row["strike_price"] = _decimal(cells[col["StrikePrice"]]) if cells[col["StrikePrice"]] else Decimal(0)
            if "Net Qty" in col and row["buy_qty"] - row["sell_qty"] != int(_decimal(cells[col["Net Qty"]])):
                raise ClosingRateError(f"line {number}: Buy Qty - Sale Qty does not equal Net Qty")
            if "Net Value" in col and abs(row["sell_value"] - row["buy_value"]
                                          - _decimal(cells[col["Net Value"]])) > VALUE_TOLERANCE:
                raise ClosingRateError(f"line {number}: Sale Value - Buy Value does not equal Net Value")
        elif first.startswith("* Totals") or (totals is None and first.startswith("** ") and "Total" in first):
            totals = {
                "buy_qty": int(_decimal(cells[col["Buy Qty"]])), "buy_value": _decimal(cells[col["Buy Value"]]),
                "sell_qty": int(_decimal(cells[col["Sale Qty"]])), "sell_value": _decimal(cells[col["Sale Value"]]),
            }
    if not rows:
        raise ClosingRateError("No contract rows found in the report.")
    if totals is None:
        raise ClosingRateError("Report totals row not found; the file may be incomplete.")
    return {"as_of": as_of, "client": client, "rows": rows, "totals": totals}


class _Silent:
    """xlrd writes harmless OLE warnings for these broker files; swallow them."""

    def write(self, *_):
        pass


def parse_report(content, filename):
    name = (filename or "").lower()
    if name.endswith(".xls"):
        report = parse_xls_report(content)
    elif name.endswith(".csv"):
        report = parse_csv_report(content)
    else:
        try:
            report = parse_net_position(content.decode("utf-8", errors="replace"))
        except CarryForwardError as exc:
            raise ClosingRateError(str(exc)) from exc
        return report  # parse_net_position already verified rows against the totals

    sums = {
        "buy_qty": sum(r["buy_qty"] for r in report["rows"]), "sell_qty": sum(r["sell_qty"] for r in report["rows"]),
        "buy_value": sum(r["buy_value"] for r in report["rows"]),
        "sell_value": sum(r["sell_value"] for r in report["rows"]),
    }
    for field, total in report["totals"].items():
        if abs(Decimal(sums[field]) - Decimal(total)) > VALUE_TOLERANCE:
            raise ClosingRateError(f"Rows do not add up to the report total {field}: rows {sums[field]}, report {total}.")
    seen = set()
    for row in report["rows"]:
        key = (row["underlying"], row["expiry"], row["strike"], row["option_type"])
        if key in seen:
            raise ClosingRateError(f"line {row['line']}: duplicate contract {key}")
        seen.add(key)
        if row["close_rate"] <= 0:
            raise ClosingRateError(f"line {row['line']}: no Close Rate for {key}")
    return report


class ClosingRateStore:
    """Imports the daily net position report (day totals per contract + Close Rates)."""

    def __init__(self, db):
        self.prices = db["market_prices"]
        self.net = db["net_positions"]
        self.carry_forward = CarryForwardStore(db)

    def ensure_indexes(self):
        self.net.create_index([("exchange", ASCENDING), ("trade_date", ASCENDING)], name="ix_np_exchange_date")

    def dates(self):
        """{exchange: sorted dates that have a net position report}."""
        return {doc["_id"]: sorted(doc["dates"]) for doc in self.net.aggregate([
            {"$group": {"_id": "$exchange", "dates": {"$addToSet": "$trade_date"}}}])}

    def _previous_day(self, exchange, before):
        """Latest day before ``before`` with data for ``exchange`` (a report or the C/F date)."""
        candidates = []
        doc = self.net.find_one({"exchange": exchange, "trade_date": {"$lt": before}}, {"trade_date": 1},
                                sort=[("trade_date", -1)])
        if doc:
            candidates.append(doc["trade_date"])
        cutoff = self.carry_forward.cutoffs().get(exchange)
        if cutoff and cutoff < before:
            candidates.append(cutoff)
        return max(candidates) if candidates else None

    @staticmethod
    def _weekdays_between(first, last):
        day, end, missing = date.fromisoformat(first) + timedelta(days=1), date.fromisoformat(last), []
        while day < end:
            if day.weekday() < 5:
                missing.append(day.isoformat())
            day += timedelta(days=1)
        return missing

    def import_report(self, content, filename=None):
        report = parse_report(content, filename)
        day = report["as_of"]
        cutoffs = self.carry_forward.cutoffs()

        by_exchange = defaultdict(list)
        for row in report["rows"]:
            by_exchange[exchange_for(row["underlying"])].append(row)
        early = [ex for ex in by_exchange if cutoffs.get(ex) and day <= cutoffs[ex]]
        if early:
            raise ClosingRateError(
                f"The report is for {day}, on or before the Carry Forward date "
                f"{max(cutoffs[ex] for ex in early)} ({', '.join(sorted(early))}); the C/F already covers that day.")

        gaps = {}
        for exchange in by_exchange:
            previous = self._previous_day(exchange, day)
            missing = self._weekdays_between(previous, day) if previous else []
            if missing:
                gaps[exchange] = missing

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        docs = []
        for exchange, rows in by_exchange.items():
            for row in rows:
                identity = {
                    "exchange": exchange,
                    "symbol": _symbol(row["underlying"], row["expiry"], row["instrument_name"]),
                    "expiry": row["expiry"], "strike": row["strike"], "option_type": row["option_type"],
                }
                docs.append({
                    "_id": f"{day}|{exchange}|{identity['symbol']}|{identity['expiry']}|{identity['strike']}|"
                           f"{identity['option_type']}",
                    **identity, "trade_date": day, "expiry_date": _iso_expiry(identity["expiry"]),
                    "instrument_name": row["instrument_name"], "underlying": row["underlying"],
                    "buy_qty": int(row["buy_qty"]), "buy_value": float(row["buy_value"]),
                    "sell_qty": int(row["sell_qty"]), "sell_value": float(row["sell_value"]),
                    "close_rate": float(row["close_rate"]),
                    # The report's own columns, kept as reported.
                    "net_qty": int(row.get("net_qty", row["buy_qty"] - row["sell_qty"])),
                    "net_value": float(row.get("net_value", row["sell_value"] - row["buy_value"])),
                    "avg_rate": float(row["avg_rate"]) if row.get("avg_rate") is not None else None,
                    "mtm": float(row["mtm"]) if row.get("mtm") is not None else None,
                    "strike_price": float(row.get("strike_price", row["strike"] or 0)),
                    "report_exchange": row.get("report_exchange"),
                    "group": row.get("group"),
                    "client": report.get("client"),
                    "source_file": filename, "source_line": row.get("line"), "imported_at": now,
                })
                if row["close_rate"] > 0:
                    self.prices.update_one({**identity, "date": day}, {"$set": {
                        "ltp": float(row["close_rate"]), "source": SOURCE, "source_file": filename, "updated_at": now,
                    }}, upsert=True)
        self.net.delete_many({"trade_date": day, "exchange": {"$in": sorted(by_exchange)}})
        if docs:
            self.net.insert_many(docs, ordered=True)

        totals = {ex: {field: _number(sum(Decimal(r[field]) for r in rows))
                       for field in ("buy_qty", "sell_qty", "buy_value", "sell_value")}
                  for ex, rows in sorted(by_exchange.items())}
        return {
            "date": day,
            "client": report.get("client"),
            "contracts": len(docs),
            "closing_rates": sum(1 for d in docs if d["close_rate"] > 0),
            "by_exchange": {ex: len(rows) for ex, rows in sorted(by_exchange.items())},
            "totals": totals,
            "missing_days": gaps,
        }

    def status(self):
        """One entry per (date, exchange) with a net position report, newest first."""
        rows = self.net.aggregate([
            {"$group": {"_id": {"date": "$trade_date", "exchange": "$exchange"}, "n": {"$sum": 1},
                        "file": {"$first": "$source_file"}, "imported_at": {"$max": "$imported_at"},
                        "buy_value": {"$sum": "$buy_value"}, "sell_value": {"$sum": "$sell_value"}}},
            {"$sort": {"_id.date": -1, "_id.exchange": 1}},
        ])
        return [{"date": r["_id"]["date"], "exchange": r["_id"]["exchange"], "contracts": r["n"],
                 "closing_rates": r["n"], "source_file": r["file"], "imported_at": r["imported_at"],
                 "buy_value": _number(r["buy_value"]), "sell_value": _number(r["sell_value"]),
                 "net_position": True} for r in rows]

    def rows(self, exchange, day, search="", sort="line", order="asc", limit=100, skip=0):
        """The net position rows of one exchange and day, as in the broker report."""
        query = {"exchange": exchange, "trade_date": day}
        search = str(search or "").strip()
        if search:
            pattern = re.escape(search)
            query["$or"] = [{field: {"$regex": pattern, "$options": "i"}}
                            for field in ("symbol", "underlying", "instrument_name", "expiry", "option_type")]
            query["$or"].append({"$expr": {"$regexMatch": {
                "input": {"$toString": "$strike"}, "regex": pattern, "options": "i"}}})
        direction = 1 if order == "asc" else -1
        fields = ROW_SORT_FIELDS.get(sort, ROW_SORT_FIELDS["line"])
        spec = [(name, direction) for name in fields] + [("_id", 1)]
        total = self.net.count_documents(query)
        totals = next(iter(self.net.aggregate([
            {"$match": query},
            {"$group": {"_id": None, **{f: {"$sum": f"${f}"} for f in (
                "buy_qty", "buy_value", "sell_qty", "sell_value", "net_qty", "net_value", "mtm")}}},
        ])), {})
        totals.pop("_id", None)
        docs = list(self.net.find(query, {"imported_at": 0}).sort(spec).skip(skip).limit(limit))
        return {"exchange": exchange, "date": day, "total": total, "rows": docs,
                "totals": {k: _number(v or 0) for k, v in totals.items()}}

def _iso_expiry(expiry):
    """'03 NOV 2026' -> '2026-11-03' (sortable)."""
    day, month, year = expiry.split()
    return f"{year}-{MONTHS.index(month) + 1:02d}-{int(day):02d}"


def _number(value):
    value = float(value)
    return int(value) if value.is_integer() else round(value, 2)
