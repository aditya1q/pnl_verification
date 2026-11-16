"""Backoffice reporting: Net Value, Realized P&L and Unrealized P&L.

Input: the Carry Forward (``carry_forward``) as the opening position and the
broker's daily net position report (``net_positions``, one row per contract
and day with that day's Buy/Sale quantity and value and the Close Rate).

- Buy Value / Sell Value: the day's Buy / Sale Value from the net position
  report. Net Value = Sell Value - Buy Value (the broker's convention: negative
  means net buying); the C/F opening value is reported separately. It is a
  cash-flow figure, not P&L.
- Realized / Unrealized P&L follow the broker's net-position method (see
  ``broker_pnl``): all terminals of the account are pooled per contract, a
  position carried in from the previous day squares off first at the day's
  average opposite price, the rest of the day uses average-price matching, and
  what stays open is carried forward at its average price.
- Unrealized P&L marks the open quantity at the end of the as-of date to that
  date's LTP: long (LTP - avg) x qty, short (avg - LTP) x qty. A position whose
  newest price is older than the as-of date is counted in ``stale_ltp``.
- MTM P&L (day / month / period) = realized + change in unrealized.

Carry Forward (month-to-month cycle): the imported C/F (``carry_forward``) is
the opening position of the account at the C/F Close Rate. Trades on or before
the C/F date are excluded; the C/F opening value is reported separately for the
period that includes the cycle start. Without a C/F, positions start flat.

LTP: the latest price stored in ``market_prices`` up to the as-of date: the
broker's Close Rate from the net position report (source BROKER_CLOSE) or a
manual LTP, falling back to the C/F Close Rate. A contract that did not trade
on a day is not in that day's report and keeps its last known price.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from .bhavcopy import BhavcopyStore
from .broker_pnl import apply_day_lots, settle_lots
from .carry_forward import CarryForwardStore
from .closing_rates import ClosingRateStore
from .opening_pnl import OpeningPnlStore

EXCHANGES = ("NSE", "BSE")

DAILY_SORT_FIELDS = (
    "date", "buy_value", "sell_value", "net_value", "gross_profit", "gross_loss",
    "realized_pnl", "unrealized_pnl", "mtm_pnl", "broker_mtm", "matched_qty", "matched_trades",
)
MONTHLY_SORT_FIELDS = (
    "month", "buy_value", "sell_value", "opening_value", "net_value", "realized_pnl",
    "unrealized_pnl", "mtm_pnl", "broker_mtm", "matched_trades", "trading_days",
)

POSITION_SORT_FIELDS = ("symbol", "side", "open_qty", "avg_price", "ltp", "unrealized_pnl")

CONTRACT_FIELDS = ("symbol", "expiry", "strike", "option_type")
IDENTITY_FIELDS = (*CONTRACT_FIELDS, "instrument_name", "underlying")


@dataclass
class ReportFilters:
    exchange: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    symbol: str | None = None
    instrument: str | None = None

    def _common(self, query):
        if self.exchange:
            query["exchange"] = self.exchange
        if self.symbol:
            query["symbol"] = self.symbol
        if self.instrument:
            query["instrument_name"] = self.instrument
        return query

    def _dates(self, field):
        bounds = {}
        if self.date_from:
            bounds["$gte"] = self.date_from
        if self.date_to:
            bounds["$lte"] = self.date_to
        return {field: bounds} if bounds else {}

    def day_query(self):
        """Symbol / instrument / date filters for ``net_positions`` (exchange added per call)."""
        query = self._common(self._dates("trade_date"))
        query.pop("exchange", None)
        return query

    def contract_query(self):
        """Symbol / instrument filters only (for C/F opening positions)."""
        query = self._common({})
        query.pop("exchange", None)
        return query

    def in_range(self, day):
        return (not self.date_from or day >= self.date_from) and (not self.date_to or day <= self.date_to)


def normalize_strike(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def contract_key(doc, exchange=None):
    return (
        exchange or doc.get("exchange"),
        doc.get("symbol"),
        doc.get("expiry"),
        normalize_strike(doc.get("strike")),
        doc.get("option_type"),
    )


def _json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _money(value):
    return round(float(value or 0), 2)


def _qty(value):
    value = float(value or 0)
    return int(value) if value.is_integer() else value


# Day totals from the daily net position report (one row per contract and day).
VALUE_FIELDS = ("buy_qty", "sell_qty", "buy_value", "sell_value")
REPORT_VALUE_GROUP = {field: {"$sum": f"${field}"} for field in VALUE_FIELDS}


def _value_fields(doc):
    buy_value = float(doc.get("buy_value") or 0)
    sell_value = float(doc.get("sell_value") or 0)
    return {
        "buy_qty": int(doc.get("buy_qty") or 0),
        "sell_qty": int(doc.get("sell_qty") or 0),
        "buy_value": _money(buy_value),
        "sell_value": _money(sell_value),
        # Broker convention (net position report): Sell - Buy, negative = net buying.
        "net_value": _money(sell_value - buy_value),
    }


def _empty_realized():
    return {"gross_profit": 0.0, "gross_loss": 0.0, "realized_pnl": 0.0, "matched_qty": 0, "matched_trades": 0}


def _empty_unrealized():
    return {"unrealized_pnl": 0.0, "open_positions": 0, "open_long_qty": 0, "open_short_qty": 0,
            "missing_ltp": 0, "stale_ltp": 0}


def _unrealized(qty, value, ltp):
    """Open qty (signed) at cost ``value`` marked to ``ltp``."""
    return ltp * qty - value if qty > 0 else value + ltp * qty


def _sort_number(value):
    return value if value is not None else float("-inf")


class Backoffice:
    def __init__(self, db):
        self.db = db
        self.market_prices = db["market_prices"]
        self.carry_forward = CarryForwardStore(db)
        self.closing_rates = ClosingRateStore(db)
        self.net = self.closing_rates.net
        self.opening_pnl = OpeningPnlStore(db)
        self.bhavcopy = BhavcopyStore(db)

    @staticmethod
    def _exchanges(filters):
        return [filters.exchange] if filters.exchange else list(EXCHANGES)

    @staticmethod
    def _day_match(filters, exchange, cutoffs, *, use_range=True, upto=None):
        """``net_positions`` query for one exchange. Days on or before the exchange's
        C/F date are never included: the C/F opening position already represents them."""
        query = filters.day_query()
        bounds = dict(query.pop("trade_date", {})) if use_range else {}
        if upto:
            bounds["$lte"] = min(bounds.get("$lte", upto), upto)
        if cutoffs.get(exchange):
            bounds["$gt"] = cutoffs[exchange]
        if bounds:
            query["trade_date"] = bounds
        return {"exchange": exchange, **query}

    # --------------------------------------------------------- building blocks
    def _trade_values(self, filters, by_day=False):
        rows = defaultdict(lambda: defaultdict(float))
        cutoffs = self.carry_forward.cutoffs()
        for name in self._exchanges(filters):
            for doc in self.net.aggregate([
                {"$match": self._day_match(filters, name, cutoffs)},
                {"$group": {"_id": "$trade_date" if by_day else None, **REPORT_VALUE_GROUP}},
            ]):
                target = rows[doc["_id"]]
                for field in VALUE_FIELDS:
                    target[field] += doc.get(field) or 0
        return rows

    def _ledger(self, filters, upto=None):
        """Broker-method ledger, one entry per contract (all terminals of the account pooled).

        Returns {contract_key: entry}; entry["days"] is [(date, record)] ascending, each
        record holding that day's opening position, trade totals, realised figures and
        closing position. ``filters`` dates do not limit the ledger (positions must carry
        from the start); only ``upto`` does.

        A contract in the Carry Forward starts from the C/F position (one lot at the
        broker's original cost, else at the C/F Close Rate): its first record is the
        C/F date with that position as closing balance. Positions are FIFO queues of
        day-lots (``broker_pnl.apply_day_lots``). On a contract's expiry day, whatever
        is still open is settled at the bhavcopy settlement price and realised.
        """
        entries = {}
        cutoffs = self.carry_forward.cutoffs()

        def entry_for(key, name, ident):
            return entries.setdefault(key, {"meta": {
                "exchange": name, **{field: ident.get(field) for field in IDENTITY_FIELDS},
            }, "trades": {}, "opening": None})

        for name in self._exchanges(filters):
            cutoff = cutoffs.get(name)
            if cutoff and (not upto or cutoff <= upto):
                # Broker's original average cost of the C/F (P&L report), else the C/F Close Rate.
                costs = self.opening_pnl.costs(cutoff)
                cf_lots = self.opening_pnl.lots(cutoff) if costs else {}
                for position in self.carry_forward.positions(name, filters.contract_query()):
                    found = entry_for(contract_key(position, name), name, position)
                    cost = costs.get(position["_id"], position["value"])
                    found["opening"] = (cutoff, position["qty"], cost, position["price"], position["value"])
                    found["broker_cost"] = position["_id"] in costs
                    lots = cf_lots.get(position["_id"])
                    if lots and abs(sum(q for q, _ in lots) - position["qty"]) < 1e-6                             and abs(sum(abs(q) * p for q, p in lots) - cost) < 0.05:
                        found["opening_lots"] = [list(l) for l in lots]  # FIFO lots, oldest first

        group_id = {"date": "$trade_date", **{field: f"${field}" for field in IDENTITY_FIELDS}}
        for name in self._exchanges(filters):
            for doc in self.net.aggregate([
                {"$match": self._day_match(filters, name, cutoffs, use_range=False, upto=upto)},
                {"$group": {"_id": group_id, **REPORT_VALUE_GROUP}},
            ]):
                ident = doc["_id"]
                found = entry_for(contract_key(ident, name), name, ident)
                totals = found["trades"].setdefault(ident["date"], [0, 0.0, 0, 0.0])
                totals[0] += doc.get("buy_qty") or 0
                totals[1] += doc.get("buy_value") or 0
                totals[2] += doc.get("sell_qty") or 0
                totals[3] += doc.get("sell_value") or 0

        settlements = self.bhavcopy.settlement_prices(upto)
        for key, found in entries.items():
            lots = []
            records = []
            if found["opening"]:
                day, qty, value = found["opening"][:3]
                lots = found.get("opening_lots") or ([[qty, value / abs(qty)]] if qty else [])
                records.append((day, {
                    "opening_qty": 0, "opening_value": 0.0, "buy_qty": 0, "buy_value": 0.0,
                    "sell_qty": 0, "sell_value": 0.0, "realised_pnl": 0.0, "realised_qty": 0,
                    "realised_buy_value": 0.0, "realised_sell_value": 0.0,
                    "closing_qty": qty, "closing_value": value, "closing_lots": [l[:] for l in lots],
                    "carry_forward": True,
                }))
            settle = settlements.get(key)  # (expiry date, settlement price)
            days = sorted(found["trades"])
            if settle and settle[0] not in found["trades"] and (not records or settle[0] > records[0][0]):
                days = sorted({*days, settle[0]})  # settle on expiry day even without trades
            for day in days:
                bq, bv, sq, sv = found["trades"].get(day, (0, 0.0, 0, 0.0))
                opening_qty = sum(q for q, _ in lots)
                opening_value = sum(abs(q) * p for q, p in lots)
                result = apply_day_lots(lots, bq, bv, sq, sv)
                record = {"opening_qty": opening_qty, "opening_value": opening_value, "buy_qty": bq,
                          "buy_value": bv, "sell_qty": sq, "sell_value": sv, **result}
                if settle and day == settle[0] and result["closing_qty"]:
                    settled = settle_lots(result["closing_lots"], settle[1])
                    for field in ("realised_pnl", "realised_qty", "realised_buy_value", "realised_sell_value"):
                        record[field] += settled[field]
                    record.update(closing_qty=0, closing_value=0.0, closing_lots=[],
                                  settled_qty=result["closing_qty"], settlement_price=settle[1])
                records.append((day, record))
                lots = [l[:] for l in record["closing_lots"]]
            found["days"] = records
            found["dates"] = [day for day, _ in records]
        return entries

    @staticmethod
    def _closing(entry, day):
        """Signed qty and cost value open at the end of ``day``."""
        index = bisect.bisect_right(entry["dates"], day) - 1
        if index < 0:
            return 0, 0.0, None
        record_day, record = entry["days"][index]
        return record["closing_qty"], record["closing_value"], record_day

    @staticmethod
    def _realized(ledger, filters, by_day=False):
        rows = defaultdict(_empty_realized)
        for found in ledger.values():
            for day, record in found["days"]:
                if not filters.in_range(day) or not record["realised_qty"]:
                    continue
                target = rows[day if by_day else None]
                pnl = record["realised_pnl"]
                target["realized_pnl"] += pnl
                target["gross_profit"] += max(pnl, 0)
                target["gross_loss"] += max(-pnl, 0)
                target["matched_qty"] += record["realised_qty"]
                target["matched_trades"] += 1  # contract-days with squared-off quantity
        return {key: {"gross_profit": _money(doc["gross_profit"]), "gross_loss": _money(doc["gross_loss"]),
                      "realized_pnl": _money(doc["realized_pnl"]), "matched_qty": _qty(doc["matched_qty"]),
                      "matched_trades": doc["matched_trades"]} for key, doc in rows.items()}

    def _latest_day(self, filters):
        """Latest net position date in scope (after the C/F), else the C/F date."""
        latest = None
        cutoffs = self.carry_forward.cutoffs()
        unbounded = ReportFilters(symbol=filters.symbol, instrument=filters.instrument)
        for name in self._exchanges(filters):
            doc = self.net.find_one(self._day_match(unbounded, name, cutoffs), {"trade_date": 1},
                                    sort=[("trade_date", DESCENDING)])
            day = doc["trade_date"] if doc else cutoffs.get(name)
            if day and (latest is None or day > latest):
                latest = day
        return latest

    def _price_history(self, contracts, max_date, cf_prices=None):
        """Prices for ``contracts`` up to ``max_date``.

        ``base`` holds the C/F Close Rate on the C/F date, so a carried position
        with no later price is marked at that close (unrealized 0). ``stored``
        holds ``market_prices``: the daily Close Rates (BROKER_CLOSE) and manual LTPs.
        """
        base = defaultdict(list)  # contract -> [(date, price, time, source)] ascending
        for key, (day, close) in (cf_prices or {}).items():
            if key in contracts and day <= max_date:
                base[key].append((day, close, None, "CF_CLOSE"))

        stored = defaultdict(list)  # contract -> [(date, ltp, source)] ascending
        for doc in self.market_prices.find({"symbol": {"$in": sorted({c[1] for c in contracts})},
                                            "date": {"$lte": max_date}}):
            key = contract_key(doc)
            if key in contracts:
                stored[key].append((doc["date"], doc["ltp"], doc.get("source") or "MANUAL"))
        for series in stored.values():
            series.sort(key=lambda item: item[0])
        return base, stored

    @staticmethod
    def _resolve_ltp(key, day, base, stored):
        """Price of ``key`` at the end of ``day``: the latest stored price (Close Rate or
        manual LTP) up to that day, else the C/F Close Rate."""
        def latest(series):
            if not series:
                return None
            index = bisect.bisect_right([item[0] for item in series], day) - 1
            return series[index] if index >= 0 else None

        fallback = latest(base.get(key))
        price = latest(stored.get(key))
        if price and (not fallback or price[0] >= fallback[0]):
            return {"ltp": price[1], "ltp_source": price[2], "ltp_date": price[0], "ltp_time": None}
        if fallback:
            return {"ltp": fallback[1], "ltp_source": fallback[3], "ltp_date": fallback[0], "ltp_time": None}
        return {"ltp": None, "ltp_source": None, "ltp_date": None, "ltp_time": None}

    def _mark_to_market(self, ledger, as_of_dates, with_rows=False):
        """Unrealized P&L per as-of date, optionally with one row per open position."""
        as_of_dates = sorted({day for day in as_of_dates if day})
        if not as_of_dates:
            return {}
        open_by_day = {day: [] for day in as_of_dates}
        for key, found in ledger.items():
            for day in as_of_dates:
                qty, value, position_date = self._closing(found, day)
                if qty:
                    open_by_day[day].append((key, found["meta"], qty, value, position_date))
        contracts = {item[0] for items in open_by_day.values() for item in items}
        cf_prices = {key: (found["opening"][0], found["opening"][3])
                     for key, found in ledger.items() if found.get("opening")}
        base, stored = (self._price_history(contracts, max(as_of_dates), cf_prices)
                        if contracts else ({}, {}))

        output = {}
        for day in as_of_dates:
            totals = _empty_unrealized()
            rows = []
            unrealized_total = 0.0
            for key, meta, qty, value, position_date in open_by_day[day]:
                price = self._resolve_ltp(key, day, base, stored)
                pnl = _unrealized(qty, value, price["ltp"]) if price["ltp"] is not None else None
                unrealized_total += pnl or 0.0
                totals["open_positions"] += 1
                if qty > 0:
                    totals["open_long_qty"] += qty
                else:
                    totals["open_short_qty"] += -qty
                if price["ltp"] is None:
                    totals["missing_ltp"] += 1
                elif price["ltp_date"] < day:
                    totals["stale_ltp"] += 1
                if with_rows:
                    rows.append({
                        **meta,
                        "carried_forward": bool(ledger[key].get("opening")),
                        "side": "LONG" if qty > 0 else "SHORT",
                        "open_qty": _qty(abs(qty)),
                        "avg_price": round(value / abs(qty), 4),
                        "open_value": _money(value),
                        **price,
                        "unrealized_pnl": _money(pnl) if pnl is not None else None,
                        "position_date": position_date,
                    })
            totals["open_long_qty"] = _qty(totals["open_long_qty"])
            totals["open_short_qty"] = _qty(totals["open_short_qty"])
            totals["unrealized_pnl"] = _money(unrealized_total)
            if with_rows:
                totals["rows"] = rows
            output[day] = totals
        return output

    def _as_of(self, filters):
        return filters.date_to or self._latest_day(filters)

    @staticmethod
    def _opening(ledger, filters):
        """C/F opening balance of the cycle, and whether the period in ``filters`` includes it.

        Opening value is signed like a cash flow: a long C/F counts as bought value (+),
        a short C/F as sold value (-), both at the C/F Close Rate. ``cost_basis`` says
        whether the positions are carried at the broker's original cost (P&L report
        imported) or at the C/F Close Rate.
        """
        openings = [found["opening"] for found in ledger.values() if found.get("opening")]
        if not openings:
            return {"cf_as_of": None, "cycle_start": None, "opening_included": False, "opening_value": 0.0,
                    "opening_positions": 0, "opening_long_qty": 0, "opening_short_qty": 0, "cost_basis": None}
        as_of = max(item[0] for item in openings)
        cycle_start = min((day for found in ledger.values() for day in found["dates"] if day > as_of), default=None)
        included = (not filters.date_from
                    or (cycle_start is not None and filters.date_from <= cycle_start)
                    or (cycle_start is None and filters.date_from > as_of))
        value = sum(item[4] if item[1] > 0 else -item[4] for item in openings)
        broker_cost = any(found.get("broker_cost") for found in ledger.values())
        return {
            "cf_as_of": as_of,
            "cycle_start": cycle_start,
            "opening_included": included,
            "opening_value": _money(value) if included else 0.0,
            "opening_positions": len(openings),
            "opening_long_qty": _qty(sum(item[1] for item in openings if item[1] > 0)),
            "opening_short_qty": _qty(sum(-item[1] for item in openings if item[1] < 0)),
            "cost_basis": "BROKER_COST" if broker_cost else "CF_CLOSE",
        }

    @staticmethod
    def _previous_dates(ledger, days):
        """For each day, the previous date the ledger has a position for (None if none)."""
        all_dates = sorted({day for found in ledger.values() for day in found["dates"]})
        previous = {}
        for day in days:
            index = bisect.bisect_left(all_dates, day) - 1
            previous[day] = all_dates[index] if index >= 0 else None
        return previous

    def _opening_pnl(self, filters, cf_as_of):
        """Broker's realised / unrealised P&L as on the C/F date for the filters' contracts."""
        summary = self.opening_pnl.summary()
        if not summary or summary["as_of"] != cf_as_of:
            return None
        query = {"as_of": cf_as_of}
        if filters.exchange:
            query["exchange"] = filters.exchange
        if filters.symbol:
            query["symbol"] = filters.symbol
        if filters.instrument:
            query["instrument_name"] = filters.instrument
        totals = next(iter(self.opening_pnl.rows.aggregate([
            {"$match": query},
            {"$group": {"_id": None, "realised": {"$sum": "$realised_pnl"},
                        "unrealised": {"$sum": "$unrealised_pnl_close"}}},
        ])), {"realised": 0.0, "unrealised": 0.0})
        whole = len(query) == 1  # no exchange / symbol / instrument filter
        if whole:  # the report's own TOTALS (row sums differ by paise of rounding)
            totals = {"realised": summary["realised_pnl"], "unrealised": summary["unrealised_pnl"]}
        return {"as_of": cf_as_of, "realized_pnl": _money(totals["realised"]),
                "unrealized_pnl": _money(totals["unrealised"]),
                "total_pnl": _money(totals["realised"] + totals["unrealised"]),
                "charges": summary.get("total_charges") if whole else None,
                "net_mtm": summary.get("net_mtm") if whole else None,
                "source_file": summary.get("source_file")}

    def summary(self, filters: ReportFilters):
        as_of = self._as_of(filters)
        ledger = self._ledger(filters, upto=as_of)
        values = _value_fields(self._trade_values(filters).get(None, {}))
        realized = self._realized(ledger, filters).get(None, _empty_realized())
        opening = self._opening(ledger, filters)
        # Period P&L starts from the close before the period (the C/F date for the whole cycle).
        start = filters.date_from or opening["cycle_start"]
        before = self._previous_dates(ledger, [start]).get(start) if start else None
        marks = self._mark_to_market(ledger, [as_of, before])
        unrealized = marks.get(as_of, _empty_unrealized())
        unrealized_before = marks[before]["unrealized_pnl"] if before else 0.0

        # Cumulative like the broker: P&L as on the C/F date + everything realized since.
        opening_pnl = self._opening_pnl(filters, opening["cf_as_of"]) if opening["cf_as_of"] else None
        cycle = ReportFilters(exchange=filters.exchange, symbol=filters.symbol, instrument=filters.instrument,
                              date_to=as_of)
        realized_since_cf = self._realized(ledger, cycle).get(None, _empty_realized())["realized_pnl"]
        cumulative = None
        if opening_pnl:
            cum_realized = opening_pnl["realized_pnl"] + realized_since_cf
            cumulative = {"realized_pnl": _money(cum_realized), "unrealized_pnl": unrealized["unrealized_pnl"],
                          "total_pnl": _money(cum_realized + unrealized["unrealized_pnl"])}
        return {
            **values,
            **realized,
            **unrealized,
            **opening,
            "trade_net_value": values["net_value"],
            "previous_unrealized_pnl": unrealized_before,
            # Period P&L: realized + change in unrealized over the period.
            "mtm_pnl": _money(realized["realized_pnl"] + unrealized["unrealized_pnl"] - unrealized_before),
            # Broker's "MTM" column: realised in the period + unrealised (at cost) at its end.
            "broker_mtm": _money(realized["realized_pnl"] + unrealized["unrealized_pnl"]),
            "opening_pnl": opening_pnl,
            "cumulative": cumulative,
            "as_of": as_of,
        }

    def _day_rows(self, filters):
        ledger = self._ledger(filters, upto=filters.date_to)
        values = self._trade_values(filters, by_day=True)
        realized = self._realized(ledger, filters, by_day=True)
        days = sorted({day for day in (*values, *realized) if day})
        previous = self._previous_dates(ledger, days)
        unrealized = self._mark_to_market(ledger, [*days, *previous.values()])
        rows = []
        for day in days:
            marks = unrealized.get(day, _empty_unrealized())
            booked = realized.get(day, _empty_realized())
            before = unrealized[previous[day]]["unrealized_pnl"] if previous[day] else 0.0
            rows.append({
                "date": day,
                **_value_fields(values.get(day, {})),
                **booked,
                **marks,
                "previous_unrealized_pnl": before,
                # Day P&L: realized today + change in unrealized since the previous close.
                "mtm_pnl": _money(booked["realized_pnl"] + marks["unrealized_pnl"] - before),
                # Broker's "MTM" column for the day: realised + unrealised at the close.
                "broker_mtm": _money(booked["realized_pnl"] + marks["unrealized_pnl"]),
            })
        return ledger, rows

    def daily(self, filters: ReportFilters, sort="date", order="desc", limit=50, skip=0):
        _, rows = self._day_rows(filters)
        key = sort if sort in DAILY_SORT_FIELDS else "date"
        rows.sort(key=lambda row: (row[key], row["date"]), reverse=(order != "asc"))
        return {"total": len(rows), "rows": rows[skip: skip + limit]}

    def monthly(self, filters: ReportFilters, sort="month", order="desc", limit=50, skip=0):
        """Month-to-month P&L built from the day rows of the month.

        Unrealized is the open position at the month's last trading day; MTM P&L is
        realized in the month + change in unrealized over the month. The C/F opening
        value is shown for the month the cycle starts in (not part of Net Value).
        """
        ledger, days = self._day_rows(filters)
        opening = self._opening(ledger, filters)
        opening_month = opening["cycle_start"][:7] if opening["opening_included"] and opening["cycle_start"] else None
        months = {}
        for row in sorted(days, key=lambda item: item["date"]):
            month = months.setdefault(row["date"][:7], {
                "month": row["date"][:7], "first_date": row["date"], "trading_days": 0,
                **{name: 0 for name in ("buy_qty", "sell_qty", "matched_qty", "matched_trades")},
                **{name: 0.0 for name in ("buy_value", "sell_value", "trade_net_value", "realized_pnl",
                                          "gross_profit", "gross_loss", "mtm_pnl")},
            })
            month["trading_days"] += 1
            month["last_date"] = row["date"]
            for name in ("buy_qty", "sell_qty", "matched_qty", "matched_trades"):
                month[name] += row[name]
            for name in ("buy_value", "sell_value", "realized_pnl", "gross_profit", "gross_loss", "mtm_pnl"):
                month[name] += row[name]
            month["trade_net_value"] += row["net_value"]
            for name in ("unrealized_pnl", "open_positions", "missing_ltp", "stale_ltp"):
                month[name] = row[name]  # as of the month's last trading day
        rows = []
        for month in months.values():
            month["opening_value"] = opening["opening_value"] if month["month"] == opening_month else 0.0
            month["net_value"] = month["trade_net_value"]  # day totals only, like the broker report
            for name in ("buy_value", "sell_value", "trade_net_value", "net_value", "realized_pnl",
                         "gross_profit", "gross_loss", "mtm_pnl"):
                month[name] = _money(month[name])
            month["matched_qty"] = _qty(month["matched_qty"])
            month["broker_mtm"] = _money(month["realized_pnl"] + month.get("unrealized_pnl", 0.0))
            rows.append(month)
        key = sort if sort in MONTHLY_SORT_FIELDS else "month"
        rows.sort(key=lambda row: (row[key], row["month"]), reverse=(order != "asc"))
        return {"total": len(rows), "rows": rows[skip: skip + limit], "cf_as_of": opening["cf_as_of"]}

    def position_rows(self, filters: ReportFilters, as_of=None, sort="unrealized_pnl", order="asc",
                      limit=50, skip=0):
        as_of = as_of or self._as_of(filters)
        if not as_of:
            return {"as_of": None, "total": 0, "rows": [], "summary": _empty_unrealized()}
        ledger = self._ledger(filters, upto=as_of)
        result = self._mark_to_market(ledger, [as_of], with_rows=True)[as_of]
        rows = result.pop("rows")
        sort_keys = {
            "symbol": lambda r: (str(r["symbol"]), str(r["expiry"]), float(r["strike"] or 0), str(r["option_type"])),
            "side": lambda r: r["side"],
            "open_qty": lambda r: r["open_qty"],
            "avg_price": lambda r: r["avg_price"] or 0,
            "ltp": lambda r: _sort_number(r["ltp"]),
            "unrealized_pnl": lambda r: _sort_number(r["unrealized_pnl"]),
        }
        rows.sort(key=sort_keys.get(sort, sort_keys["unrealized_pnl"]), reverse=(order != "asc"))
        return {"as_of": as_of, "total": len(rows), "rows": _json_safe(rows[skip: skip + limit]), "summary": result}

    # ------------------------------------------------------------- manual LTP
    def set_ltp(self, exchange, symbol, expiry, strike, option_type, day, ltp):
        identity = {"exchange": exchange, "symbol": symbol, "expiry": expiry, "strike": strike,
                    "option_type": option_type, "date": day}
        self.market_prices.update_one(identity, {"$set": {
            "ltp": float(ltp), "source": "MANUAL", "source_file": None,
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }}, upsert=True)
        return identity | {"ltp": float(ltp)}

    def clear_ltp(self, exchange, symbol, expiry, strike, option_type, day):
        """Remove a manual LTP. The day's Close Rate (same price record) comes back from
        that day's net position report, if the contract is in it."""
        identity = {"exchange": exchange, "symbol": symbol, "expiry": expiry, "strike": strike,
                    "option_type": option_type, "date": day}
        report = self.net.find_one({**{k: v for k, v in identity.items() if k != "date"}, "trade_date": day,
                                    "close_rate": {"$gt": 0}})
        if report:
            self.market_prices.update_one(identity, {"$set": {
                "ltp": float(report["close_rate"]), "source": "BROKER_CLOSE", "source_file": report.get("source_file"),
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }}, upsert=True)
            return {"deleted": 1, "restored_close_rate": float(report["close_rate"])}
        result = self.market_prices.delete_one({**identity, "source": "MANUAL"})
        return {"deleted": result.deleted_count, "restored_close_rate": None}

    # ---------------------------------------------------------------- filters
    def filter_options(self, exchange=None):
        exchanges = [exchange] if exchange else list(EXCHANGES)
        cutoffs = self.carry_forward.cutoffs()
        symbols, instruments, first, last = set(), set(), None, None
        for name in exchanges:
            query = self._day_match(ReportFilters(), name, cutoffs)
            symbols.update(value for value in self.net.distinct("symbol", query) if value)
            instruments.update(value for value in self.net.distinct("instrument_name", query) if value)
            for position in self.carry_forward.positions(name):
                symbols.add(position["symbol"])
                instruments.add(position["instrument_name"])
            for direction in (ASCENDING, DESCENDING):
                doc = self.net.find_one(query, {"trade_date": 1}, sort=[("trade_date", direction)])
                if doc:
                    first = doc["trade_date"] if first is None else min(first, doc["trade_date"])
                    last = doc["trade_date"] if last is None else max(last, doc["trade_date"])
        return {
            "symbols": sorted(symbols),
            "instruments": sorted(instruments),
            "first_date": first,
            "last_date": last,
            "carry_forward": self.carry_forward.status(),
        }
