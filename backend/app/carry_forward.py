"""Carry Forward (C/F) opening positions for month-to-month P&L.

The broker's "Clientwise Net Position" report (e.g. NFO_NETPOSITION_30102026.txt)
lists, per contract, the account's open Net Qty at the close of its "As On
Date" and that day's Close Rate. Importing it starts a new P&L cycle:

- Each non-zero Net Qty becomes an opening position for the account (all
  terminals pooled), carried in at the Close Rate. P&L up to that close was
  already settled in the previous month, so the new month starts from there.
- Trades dated on or before the C/F date are excluded from the reports; the
  cycle starts with the first trading day after it.
- Re-importing a C/F file replaces the previous C/F of the same exchanges, so
  an import can never be counted twice.

Before anything is stored the report is checked: every data row must parse,
the parsed rows must add up to the report's own Buy/Sale/Net quantity and
Buy/Sale value totals, no contract may appear twice, and every open position
needs a positive Close Rate.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from pymongo import ASCENDING

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
BSE_UNDERLYINGS = {"SENSEX", "BANKEX", "SENSEX50"}
INSTRUMENTS = ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK")
NUM = r"(-?\d+(?:\.\d+)?)"
ROW = re.compile(
    r"^\s*(FUTIDX|OPTIDX|FUTSTK|OPTSTK)\s+(\S+)\s+(\d\d/\d\d/\d\d)\s+"
    r"(?:(\d+(?:\.\d+)?)\s+(CE|PE)\s+)?"
    + r"\s+".join([NUM] * 10) + r"\s*$"
)
AS_ON = re.compile(r"As On Date:\s*(\d\d)/(\d\d)/(\d{4})")
TOTALS = {
    "buy_qty": re.compile(r"Buy Qty:\s*(-?\d+)"),
    "sell_qty": re.compile(r"Sale Qty:\s*(-?\d+)"),
    "net_qty": re.compile(r"Net Qty:\s*(-?\d+)"),
    "buy_value": re.compile(r"Buy Value:\s*(-?[\d.]+)"),
    "sell_value": re.compile(r"Sale\s+Value:\s*(-?[\d.]+)"),
}
CLIENT = re.compile(r"^\s{1,6}([A-Z0-9]+)\s{3,}([A-Z0-9]+)\s*$")


class CarryForwardError(ValueError):
    pass


def exchange_for(underlying):
    return "BSE" if underlying.upper() in BSE_UNDERLYINGS else "NSE"


def _expiry(text):
    day, month, year = text.split("/")
    return f"{day} {MONTHS[int(month) - 1]} 20{year}"


def _strike(text):
    """Stored like the trade files: whole strikes as int, futures as 0."""
    if not text:
        return 0
    value = Decimal(text)
    return int(value) if value == value.to_integral_value() else float(value)


def _symbol(underlying, expiry, instrument):
    day, month, _ = expiry.split()
    return f"{underlying}{day}{month}{'FUT' if instrument.startswith('FUT') else 'OPT'}"


def parse_net_position(text):
    """Parse and verify a broker net position report.

    Returns {"as_of", "client", "rows", "totals"}; raises CarryForwardError when
    the report is incomplete or does not add up.
    """
    as_on = AS_ON.search(text)
    if not as_on:
        raise CarryForwardError("'As On Date' not found; is this a Clientwise Net Position report?")
    day, month, year = as_on.groups()
    as_of = f"{year}-{month}-{day}"

    rows, errors, client = [], [], None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if client is None and CLIENT.match(line):
            client = " / ".join(CLIENT.match(line).groups())
        if not stripped.startswith(INSTRUMENTS):
            continue
        match = ROW.match(line)
        if not match:
            errors.append(f"line {number}: could not read row: {stripped[:80]}")
            continue
        (instrument, underlying, expiry, strike, option, buy_qty, buy_value, sell_qty, sell_value,
         net_qty, net_value, avg_rate, close_rate, mtm, option_value) = match.groups()
        if instrument.startswith("OPT") and not option:
            errors.append(f"line {number}: option row without strike / option type")
            continue
        rows.append({
            "line": number,
            "instrument_name": instrument,
            "underlying": underlying,
            "expiry": _expiry(expiry),
            "strike": _strike(strike),
            "option_type": option or "FX",
            "buy_qty": int(buy_qty), "buy_value": Decimal(buy_value),
            "sell_qty": int(sell_qty), "sell_value": Decimal(sell_value),
            "net_qty": int(net_qty), "net_value": Decimal(net_value), "avg_rate": Decimal(avg_rate),
            "close_rate": Decimal(close_rate), "mtm": Decimal(mtm), "option_value": Decimal(option_value),
            "strike_price": Decimal(strike) if strike else Decimal(0),
        })
    if errors:
        raise CarryForwardError(f"{len(errors)} row(s) could not be read. First: {errors[0]}")
    if not rows:
        raise CarryForwardError("No position rows found in the report.")

    # Each row must be internally consistent, and the rows must add up to the report totals.
    for row in rows:
        if row["buy_qty"] - row["sell_qty"] != row["net_qty"]:
            raise CarryForwardError(f"line {row['line']}: Purchase Qty - Sale Qty does not equal Net Qty")
    seen = {}
    for row in rows:
        key = (row["underlying"], row["expiry"], row["strike"], row["option_type"])
        if key in seen:
            raise CarryForwardError(f"line {row['line']}: duplicate contract (also on line {seen[key]})")
        seen[key] = row["line"]
        if row["net_qty"] and row["close_rate"] <= 0:
            raise CarryForwardError(f"line {row['line']}: open position without a Close Rate")

    parsed = {
        "buy_qty": sum(r["buy_qty"] for r in rows), "sell_qty": sum(r["sell_qty"] for r in rows),
        "net_qty": sum(r["net_qty"] for r in rows),
        "buy_value": sum(r["buy_value"] for r in rows), "sell_value": sum(r["sell_value"] for r in rows),
    }
    totals = {}
    for name, pattern in TOTALS.items():
        found = pattern.search(text)
        if not found:
            raise CarryForwardError(f"Report total '{name}' not found; the file may be incomplete.")
        totals[name] = Decimal(found.group(1)) if "value" in name else int(found.group(1))
        if parsed[name] != totals[name]:
            raise CarryForwardError(
                f"Rows do not add up to the report total {name}: rows {parsed[name]}, report {totals[name]}.")
    return {"as_of": as_of, "client": client, "rows": rows, "totals": totals}


def to_positions(report, source_file=None):
    """Open positions (non-zero Net Qty) as documents for the ``carry_forward`` collection."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    positions = []
    for row in report["rows"]:
        if not row["net_qty"]:
            continue
        exchange = exchange_for(row["underlying"])
        symbol = _symbol(row["underlying"], row["expiry"], row["instrument_name"])
        doc = {
            "exchange": exchange,
            "symbol": symbol,
            "expiry": row["expiry"],
            "strike": row["strike"],
            "option_type": row["option_type"],
            "instrument_name": row["instrument_name"],
            "underlying": row["underlying"],
            "as_of": report["as_of"],
            "qty": row["net_qty"],
            "price": float(row["close_rate"]),
            "value": float(abs(row["net_qty"]) * row["close_rate"]),
            # The report's own columns, kept as reported.
            "buy_qty": row["buy_qty"], "buy_value": float(row["buy_value"]),
            "sell_qty": row["sell_qty"], "sell_value": float(row["sell_value"]),
            "net_qty": row["net_qty"], "net_value": float(row["net_value"]),
            "avg_rate": float(row["avg_rate"]), "close_rate": float(row["close_rate"]),
            "mtm": float(row["mtm"]), "option_value": float(row["option_value"]),
            "strike_price": float(row["strike_price"]),
            "client": report.get("client"),
            "source_file": source_file,
            "source_line": row["line"],
            "imported_at": now,
        }
        doc["_id"] = "|".join([exchange, symbol, doc["expiry"], str(doc["strike"]), doc["option_type"]])
        positions.append(doc)
    return positions


class CarryForwardStore:
    def __init__(self, db):
        self.collection = db["carry_forward"]

    def ensure_indexes(self):
        self.collection.create_index([("exchange", ASCENDING), ("as_of", ASCENDING)], name="ix_cf_exchange_as_of")

    def replace(self, positions, exchanges):
        """Replace the C/F of ``exchanges`` with ``positions`` (idempotent)."""
        self.collection.delete_many({"exchange": {"$in": sorted(exchanges)}})
        if positions:
            self.collection.insert_many(positions, ordered=True)
        return len(positions)

    def import_report(self, text, source_file=None):
        report = parse_net_position(text)
        positions = to_positions(report, source_file)
        exchanges = {exchange_for(row["underlying"]) for row in report["rows"]}
        self.replace(positions, exchanges)
        return {
            "as_of": report["as_of"],
            "client": report["client"],
            "rows": len(report["rows"]),
            "open_positions": len(positions),
            "by_exchange": {ex: sum(1 for p in positions if p["exchange"] == ex) for ex in sorted(exchanges)},
            "totals_verified": {k: float(v) if isinstance(v, Decimal) else v for k, v in report["totals"].items()},
        }

    def cutoffs(self):
        """{exchange: C/F as-of date}. Trades on or before it are excluded from reports."""
        return {doc["_id"]: doc["as_of"] for doc in self.collection.aggregate([
            {"$group": {"_id": "$exchange", "as_of": {"$max": "$as_of"}}}])}

    def positions(self, exchange, query=None):
        return list(self.collection.find({"exchange": exchange, **(query or {})}))

    def status(self):
        rows = list(self.collection.aggregate([{"$group": {
            "_id": {"exchange": "$exchange", "as_of": "$as_of"},
            "positions": {"$sum": 1}, "client": {"$first": "$client"},
            "source_file": {"$first": "$source_file"}, "imported_at": {"$max": "$imported_at"},
        }}, {"$sort": {"_id.exchange": 1}}]))
        return [{"exchange": r["_id"]["exchange"], "as_of": r["_id"]["as_of"], "positions": r["positions"],
                 "client": r["client"], "source_file": r["source_file"], "imported_at": r["imported_at"]}
                for r in rows]
