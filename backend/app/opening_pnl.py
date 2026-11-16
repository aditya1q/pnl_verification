"""Broker P&L report as on the Carry Forward date (e.g. MOP117_30-10-2026.csv).

The report lists, per contract, the realised P&L up to that date and the open
(unrealised) quantity at its original average cost:

    Realised Qty / Buy Value / Sell Value / P&L
    Unrealised Qty / Buy Value / Sell Value / Value (= Sell - Buy of the open qty)
    Close Rate / Close Value (= Unrealised Qty x Close Rate)
    Unrealised P&L With CloseRate (= Close Value + Unrealised Value)
    MTM (= Realised P&L + Unrealised P&L With CloseRate)

Importing it makes the P&L cumulative like the broker's:

- the Carry Forward positions are carried at the broker's original average cost
  (Unrealised Buy Value for a long, Unrealised Sell Value for a short) instead of
  the C/F Close Rate, so later realised / unrealised P&L is measured the broker's way;
- its Realised P&L and Unrealised P&L With CloseRate are the opening P&L of the cycle.

Checks before anything is stored: every row's own arithmetic, the column
totals against the TOTALS row, and that its open positions are exactly the
imported Carry Forward (same contracts, Net Qty and Close Rate).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal

from .carry_forward import MONTHS, CarryForwardStore, _symbol, exchange_for

ROW_TOLERANCE = Decimal("1.00")  # exports may round large values to whole rupees
TOTAL_TOLERANCE = Decimal("1.00")  # column totals are rounded row by row (paise)
NAME = re.compile(r"^(FUTIDX|OPTIDX|FUTSTK|OPTSTK)([A-Z0-9&]+?)(\d{2})([A-Z]{3})(\d{4})$")
DATE_IN_NAME = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
COLUMNS = {
    "Realised Qty": "realised_qty", "Realised Buy Value": "realised_buy_value",
    "Realised Sell Value": "realised_sell_value", "Realised P&L": "realised_pnl",
    "Unrealised Qty": "unrealised_qty", "Unrealised Buy Value": "unrealised_buy_value",
    "Unrealised Sell Value": "unrealised_sell_value", "Unrealised Value": "unrealised_value",
    "Close Rate": "close_rate", "Close Value": "close_value",
    "Unrealised P&L With CloseRate": "unrealised_pnl_close", "Unrealised P&L": "unrealised_pnl_report",
    "Realised+Unrealised": "realised_plus_unrealised", "MTM": "mtm",
}


class OpeningPnlError(ValueError):
    pass


def _num(text):
    text = str(text or "").replace(",", "").strip()
    return Decimal(text) if text else Decimal(0)


def _xls_to_csv(content):
    """The broker's .XLS export (Excel 97) as CSV text, numbers without trailing '.0'."""
    import xlrd

    class _Silent:
        def write(self, *_):
            pass

    sheet = xlrd.open_workbook(file_contents=content, logfile=_Silent()).sheet_by_index(0)
    out = io.StringIO()
    writer = csv.writer(out)
    for r in range(sheet.nrows):
        writer.writerow([str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()
                         for v in sheet.row_values(r)])
    return out.getvalue()


def parse_pnl_report(content, filename=None):
    if isinstance(content, bytes) and content[:4] == b"\xd0\xcf\x11\xe0":  # .XLS (OLE2)
        content = _xls_to_csv(content)
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    lines = list(csv.reader(io.StringIO(text)))
    # The header row may follow title lines ("NSE FO Realised & Unrealised - Client: ...").
    start = next((i for i, cells in enumerate(lines[:10])
                  if [c.strip() for c in cells[:4]] == ["Client Code", "Security Name", "Option Type", "Strike Price"]), None)
    if start is None:
        raise OpeningPnlError("Not a broker P&L report: expected 'Client Code, Security Name, Option Type, Strike Price, ...'.")
    header = [c.strip() for c in lines[start]]
    lines = lines[start:]
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        raise OpeningPnlError(f"Report columns missing: {', '.join(missing)}")
    col = {name: header.index(name) for name in header}

    rows, totals, charges, errors, seen = [], None, {}, [], set()
    for number, cells in enumerate(lines[1:], start=2):
        if not cells or not any(c.strip() for c in cells):
            continue
        first = cells[0].strip()
        if first == "TOTALS":
            totals = {field: _num(cells[col[name]]) for name, field in COLUMNS.items() if cells[col[name]].strip()}
            continue
        if not first:  # charges block: label in one column, amount in the next
            filled = [c.strip() for c in cells if c.strip()]
            if len(filled) == 2:
                try:
                    charges[filled[0]] = float(_num(filled[1]))
                except Exception:
                    pass
            continue
        match = NAME.match(cells[col["Security Name"]].strip())
        if not match:
            errors.append(f"line {number}: unknown security {cells[col['Security Name']]!r}")
            continue
        instrument, underlying, day, month, year = match.groups()
        if month not in MONTHS:
            errors.append(f"line {number}: unknown expiry month {month!r}")
            continue
        option = cells[col["Option Type"]].strip() or "FX"
        strike = _num(cells[col["Strike Price"]])
        strike = 0 if option == "FX" else (int(strike) if strike == strike.to_integral_value() else float(strike))
        row = {"line": number, "client": first, "security_name": cells[col["Security Name"]].strip(),
               "instrument_name": instrument, "underlying": underlying, "expiry": f"{day} {month} {year}",
               "option_type": option, "strike": strike,
               **{field: _num(cells[col[name]]) for name, field in COLUMNS.items()}}
        r = row
        checks = (
            ("Realised P&L = Sell - Buy", r["realised_sell_value"] - r["realised_buy_value"], r["realised_pnl"]),
            ("Unrealised Value = Sell - Buy", r["unrealised_sell_value"] - r["unrealised_buy_value"], r["unrealised_value"]),
            ("Close Value = Qty x Close Rate", r["unrealised_qty"] * r["close_rate"], r["close_value"]),
            ("Unrealised P&L With CloseRate", r["close_value"] + r["unrealised_value"], r["unrealised_pnl_close"]),
            ("MTM = Realised + Unrealised", r["realised_pnl"] + r["unrealised_pnl_close"], r["mtm"]),
        )
        for label, expected, reported in checks:
            if abs(expected - reported) > ROW_TOLERANCE:
                errors.append(f"line {number}: {label} does not add up ({expected} vs {reported})")
        key = (underlying, row["expiry"], strike, option)
        if key in seen:
            errors.append(f"line {number}: duplicate contract {key}")
        seen.add(key)
        rows.append(row)
    if errors:
        raise OpeningPnlError(f"{len(errors)} problem(s) in the report. First: {errors[0]}")
    if not rows:
        raise OpeningPnlError("No contract rows found in the report.")
    if totals is None:
        raise OpeningPnlError("TOTALS row not found; the file may be incomplete.")
    for field, total in totals.items():
        if field == "close_rate":
            continue
        rows_sum = sum(r[field] for r in rows)
        if abs(rows_sum - total) > TOTAL_TOLERANCE:
            raise OpeningPnlError(f"Rows do not add up to the TOTALS row for {field}: rows {rows_sum}, report {total}.")

    as_of = None
    found = DATE_IN_NAME.search(filename or "")
    if found:
        day, month, year = found.groups()
        as_of = f"{year}-{month}-{day}"
    return {"rows": rows, "totals": totals, "charges": charges, "as_of": as_of,
            "client": rows[0]["client"]}


def contract_id(exchange, row):
    symbol = _symbol(row["underlying"], row["expiry"], row["instrument_name"])
    return "|".join([exchange, symbol, row["expiry"], str(row["strike"]), row["option_type"]]), symbol


class OpeningPnlStore:
    """``opening_pnl``: one document per contract of the report; ``opening_pnl_summary``:
    the report totals and charges. Both replaced on every import."""

    def __init__(self, db):
        self.rows = db["opening_pnl"]
        self.summary_collection = db["opening_pnl_summary"]
        self.cf_lots = db["cf_lots"]  # C/F split into FIFO day-lots (oldest first), optional
        self.carry_forward = CarryForwardStore(db)

    def import_report(self, content, filename=None):
        report = parse_pnl_report(content, filename)
        cf = {doc["_id"]: doc for doc in self.carry_forward.collection.find()}
        if not cf:
            raise OpeningPnlError("Import the Carry Forward net position first; this report is checked against it.")
        cf_dates = sorted({doc["as_of"] for doc in cf.values()})
        as_of = report["as_of"] or cf_dates[-1]
        if as_of not in cf_dates:
            raise OpeningPnlError(f"The report is for {as_of} but the Carry Forward is as of {', '.join(cf_dates)}.")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        docs, problems, open_ids = [], [], set()
        for row in report["rows"]:
            exchange = exchange_for(row["underlying"])
            ident, symbol = contract_id(exchange, row)
            qty = int(row["unrealised_qty"])
            if qty:
                open_ids.add(ident)
                position = cf.get(ident)
                if position is None:
                    problems.append(f"{ident}: open qty {qty} but not in the Carry Forward")
                elif position["qty"] != qty:
                    problems.append(f"{ident}: open qty {qty}, Carry Forward Net Qty {position['qty']}")
                elif abs(Decimal(str(position["price"])) - row["close_rate"]) > Decimal("0.001"):
                    problems.append(f"{ident}: Close Rate {row['close_rate']}, Carry Forward {position['price']}")
            cost_value = row["unrealised_buy_value"] if qty > 0 else row["unrealised_sell_value"] if qty < 0 else Decimal(0)
            docs.append({
                "_id": ident, "exchange": exchange, "symbol": symbol, "as_of": as_of,
                **{k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()},
                "unrealised_qty": qty, "realised_qty": float(row["realised_qty"]),
                "cost_value": float(cost_value),
                "cost_price": float(cost_value / abs(qty)) if qty else None,
                "source_file": filename, "source_line": row["line"], "imported_at": now,
            })
        missing = sorted(set(ident for ident in cf if cf[ident]["as_of"] == as_of) - open_ids)
        if missing:
            problems.append(f"{len(missing)} Carry Forward position(s) not open in the report, e.g. {missing[0]}")
        if problems:
            raise OpeningPnlError(f"The report does not match the Carry Forward ({len(problems)} problem(s)). "
                                  f"First: {problems[0]}")

        self.rows.delete_many({})
        self.rows.insert_many(docs, ordered=True)
        totals = {k: float(v) for k, v in report["totals"].items()}
        summary = {
            "_id": as_of, "as_of": as_of, "client": report["client"], "contracts": len(docs),
            "open_positions": len(open_ids), "totals": totals, "charges": report["charges"],
            "realised_pnl": totals.get("realised_pnl", 0.0),
            "unrealised_pnl": totals.get("unrealised_pnl_close", 0.0),
            "mtm": totals.get("mtm", 0.0),
            "total_charges": report["charges"].get("TOTAL CHRGES"),
            "net_mtm": report["charges"].get("NET MTM"),
            "source_file": filename, "imported_at": now,
        }
        self.summary_collection.delete_many({})
        self.summary_collection.insert_one(summary)
        return summary

    def summary(self):
        return self.summary_collection.find_one({}, sort=[("as_of", -1)])

    def lots(self, as_of):
        """{contract id: [[signed qty, price], ...] oldest first} for the C/F date (``cf_lots``)."""
        return {doc["_id"].split("@")[0]: doc["lots"] for doc in self.cf_lots.find({"as_of": as_of})}

    def save_lots(self, as_of, lots_by_id, source):
        """Store C/F lots; each contract's lots must add up to the C/F qty and the broker cost."""
        costs = {doc["_id"]: doc for doc in self.rows.find({"as_of": as_of, "unrealised_qty": {"$ne": 0}})}
        docs, problems = [], []
        for ident, lots in lots_by_id.items():
            row = costs.get(ident)
            if row is None:
                problems.append(f"{ident}: not an open C/F position")
                continue
            qty = sum(q for q, _ in lots)
            value = sum(abs(q) * p for q, p in lots)
            if abs(qty - row["unrealised_qty"]) > 1e-6 or abs(value - row["cost_value"]) > 0.05                     or len({q > 0 for q, _ in lots}) != 1:
                problems.append(f"{ident}: lots {qty} / {value:.2f} vs C/F {row['unrealised_qty']} / {row['cost_value']:.2f}")
                continue
            docs.append({"_id": f"{ident}@{as_of}", "as_of": as_of, "lots": lots, "source": source})
        if problems:
            raise OpeningPnlError(f"{len(problems)} lot problem(s). First: {problems[0]}")
        self.cf_lots.delete_many({"as_of": as_of})
        if docs:
            self.cf_lots.insert_many(docs)
        return {"as_of": as_of, "contracts": len(docs), "source": source}

    def costs(self, as_of):
        """{contract id: cost value of the open qty} for the Carry Forward date."""
        return {doc["_id"]: doc["cost_value"] for doc in self.rows.find(
            {"as_of": as_of, "unrealised_qty": {"$ne": 0}}, {"cost_value": 1})}
