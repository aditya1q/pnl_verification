"""Exchange F&O bhavcopy (UDiFF format): closing rates and expiry settlement prices.

Files (one per exchange and trading day):
    NSE  BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip
    BSE  BhavCopy_BSE_FO_0_0_0_<YYYYMMDD>_F_0000.CSV

``ClsPric`` is the exchange closing price, the same as the broker's Close Rate
(checked on all 275 contracts of 2 Nov 2026). It is stored in ``market_prices``
with source BHAVCOPY, so contracts that did not trade that day (not in the day's
net position) are still marked to the day's close. A broker Close Rate or a
manual LTP for the same date is never overwritten.

On a contract's expiry day the bhavcopy's ``SttlmPric`` is the final settlement
price: for options it is the underlying's settlement price (e.g. NIFTY 23810.85),
so an expiring option settles at its intrinsic value, max(0, S - K) for a CE and
max(0, K - S) for a PE; a future settles at ``SttlmPric``. These go into
``settlements``; the reports close any position still open on expiry day at
that price.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from pymongo import ASCENDING, UpdateOne

from .carry_forward import MONTHS, _symbol

INSTRUMENTS = {"IDF": "FUTIDX", "IDO": "OPTIDX", "STF": "FUTSTK", "STO": "OPTSTK"}
SOURCE = "BHAVCOPY"
KEEP_SOURCES = ("BROKER_CLOSE", "MANUAL")  # never overwritten by the bhavcopy
URLS = {
    "NSE": "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip",
    "BSE": "https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_{d}_F_0000.CSV",
}
FILE_NAME = re.compile(r"BhavCopy_(NSE|BSE)_FO_0_0_0_(\d{8})_F_0000", re.IGNORECASE)
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "bhavcopy"


class BhavcopyError(ValueError):
    pass


def _text(content):
    if content[:2] == b"PK":  # zip
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise BhavcopyError("The zip has no .csv bhavcopy inside.")
            return archive.read(names[0]).decode("utf-8-sig", errors="replace")
    return content.decode("utf-8-sig", errors="replace")


def _expiry(text):
    year, month, day = text.strip()[:10].split("-")
    return f"{day} {MONTHS[int(month) - 1]} {year}"


def parse_bhavcopy(content, underlyings=None):
    """Rows of a UDiFF F&O bhavcopy, optionally only for ``underlyings``."""
    reader = csv.DictReader(io.StringIO(_text(content)))
    needed = {"TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "ClsPric", "SttlmPric"}
    if not reader.fieldnames or not needed <= {f.strip() for f in reader.fieldnames}:
        raise BhavcopyError("Not a UDiFF F&O bhavcopy (TradDt, FinInstrmTp, TckrSymb, XpryDt, ... ClsPric, SttlmPric).")
    rows, days = [], set()
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        instrument = INSTRUMENTS.get(row["FinInstrmTp"])
        if not instrument:
            continue
        underlying = row["TckrSymb"]
        if underlyings and underlying not in underlyings:
            continue
        expiry = _expiry(row.get("FininstrmActlXpryDt") or row["XpryDt"])
        option = row["OptnTp"] if instrument.startswith("OPT") else "FX"
        strike = float(row["StrkPric"] or 0) if option != "FX" else 0
        if strike and float(strike).is_integer():
            strike = int(strike)
        days.add(row["TradDt"][:10])
        rows.append({
            "trade_date": row["TradDt"][:10], "instrument_name": instrument, "underlying": underlying,
            "symbol": _symbol(underlying, expiry, instrument), "expiry": expiry, "strike": strike,
            "option_type": option, "close": float(row["ClsPric"] or 0), "settle": float(row["SttlmPric"] or 0),
            "underlying_price": float(row.get("UndrlygPric") or 0),
            "expiry_date": (row.get("FininstrmActlXpryDt") or row["XpryDt"])[:10],
        })
    if len(days) > 1:
        raise BhavcopyError(f"The file covers several dates: {sorted(days)}.")
    if not rows:
        raise BhavcopyError("No F&O rows found for the traded underlyings.")
    return {"date": days.pop(), "rows": rows}


def settlement_value(row):
    """Expiry-day settlement of one contract: intrinsic value for options, SttlmPric for futures."""
    if row["option_type"] == "CE":
        return round(max(0.0, row["settle"] - row["strike"]), 2)
    if row["option_type"] == "PE":
        return round(max(0.0, row["strike"] - row["settle"]), 2)
    return row["settle"]


class BhavcopyStore:
    def __init__(self, db):
        self.prices = db["market_prices"]
        self.settlements = db["settlements"]
        self.files = db["bhavcopy_files"]
        self.db = db

    def ensure_indexes(self):
        self.settlements.create_index([("exchange", ASCENDING), ("date", ASCENDING)], name="ix_settle_exchange_date")

    def underlyings(self):
        """Underlyings the account holds or trades (only these are stored)."""
        found = set(self.db["carry_forward"].distinct("underlying"))
        found.update(self.db["net_positions"].distinct("underlying"))
        return found or None

    def import_file(self, content, filename=None, exchange=None):
        match = FILE_NAME.search(filename or "")
        exchange = (exchange or (match.group(1) if match else "")).upper()
        if exchange not in URLS:
            raise BhavcopyError("Tell which exchange the bhavcopy is for (file name BhavCopy_NSE_FO_... or BhavCopy_BSE_FO_...).")
        report = parse_bhavcopy(content, self.underlyings())
        day = report["date"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        keep = {(d["symbol"], d["expiry"], str(d["strike"]), d["option_type"])
                for d in self.prices.find({"exchange": exchange, "date": day, "source": {"$in": list(KEEP_SOURCES)}},
                                          {"symbol": 1, "expiry": 1, "strike": 1, "option_type": 1})}
        price_ops, settle_ops, settled = [], [], 0
        for row in report["rows"]:
            identity = {"exchange": exchange, "symbol": row["symbol"], "expiry": row["expiry"],
                        "strike": row["strike"], "option_type": row["option_type"], "date": day}
            if (row["symbol"], row["expiry"], str(row["strike"]), row["option_type"]) not in keep and row["close"] > 0:
                price_ops.append(UpdateOne(identity, {"$set": {
                    "ltp": row["close"], "source": SOURCE, "source_file": filename, "updated_at": now}}, upsert=True))
            if row["expiry_date"] == day:
                value = settlement_value(row)
                settle_ops.append(UpdateOne(identity, {"$set": {
                    "price": value, "underlying_settlement": row["settle"] if row["option_type"] != "FX" else None,
                    "instrument_name": row["instrument_name"], "underlying": row["underlying"],
                    "source_file": filename, "updated_at": now}}, upsert=True))
                settled += 1
        if price_ops:
            self.prices.bulk_write(price_ops, ordered=False)
        if settle_ops:
            self.settlements.bulk_write(settle_ops, ordered=False)
        summary = {"_id": f"{day}|{exchange}", "date": day, "exchange": exchange, "contracts": len(report["rows"]),
                   "closing_rates": len(price_ops), "kept_broker_or_manual": len(keep), "settlements": settled,
                   "source_file": filename, "imported_at": now}
        self.files.replace_one({"_id": summary["_id"]}, summary, upsert=True)
        return summary

    def fetch(self, day, exchanges=("NSE", "BSE"), timeout=40):
        """Download and import the bhavcopy of ``day`` (ISO date) from the exchanges' archives."""
        stamp = date.fromisoformat(day).strftime("%Y%m%d")
        results, errors = [], {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for exchange in exchanges:
            url = URLS[exchange].format(d=stamp)
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://www.nseindia.com/"})
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    content = response.read()
            except Exception as exc:  # network / not published yet / holiday
                errors[exchange] = f"download failed: {exc}"
                continue
            name = url.rsplit("/", 1)[1]
            (DATA_DIR / name).write_bytes(content)
            try:
                results.append(self.import_file(content, name, exchange))
            except BhavcopyError as exc:
                errors[exchange] = str(exc)
        return {"date": day, "imported": results, "errors": errors}

    def settlement_prices(self, upto=None):
        """{(exchange, symbol, expiry, strike, option_type): (date, price)} for expiry days."""
        query = {"date": {"$lte": upto}} if upto else {}
        return {(d["exchange"], d["symbol"], d["expiry"], str(d["strike"]), d["option_type"]): (d["date"], d["price"])
                for d in self.settlements.find(query)}

    def status(self):
        return list(self.files.find({}, {"_id": 0}).sort([("date", -1), ("exchange", 1)]))
