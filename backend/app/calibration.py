"""Calibrate the Carry Forward lots with the broker's daily P&L report.

The C/F report gives one average cost per contract (plus, from the C/F date's
trades, the lot added on that date). The broker, however, keeps every lot from
before the C/F date and closes them oldest first, so when an old C/F position is
partly closed its realised P&L can differ from ours, although quantities and the
total (realised + unrealised) always agree.

The broker's "NSE FO Realised & Unrealised" report for a day shows exactly what
the closed quantity cost. For every C/F contract whose realised P&L differs on
that day, the part of the C/F consumed that day is split off as its own lot at
the broker's cost, and the difference is moved onto the rest of the lot it came
from, so the C/F total cost is unchanged. Days must be calibrated in date order;
each calibrated day then matches the broker contract by contract, and later days
use the corrected lots.
"""
from __future__ import annotations

from .backoffice import ReportFilters, contract_key
from .carry_forward import exchange_for
from .opening_pnl import OpeningPnlError, contract_id, parse_pnl_report

QTY = 1e-6


def _split(lots, start, length):
    """Lots with breaks at unit offsets ``start`` and ``start + length``; returns (lots, first, last) indexes."""
    out, pos = [], 0.0
    for qty, price in lots:
        size = abs(qty)
        sign = 1 if qty > 0 else -1
        cuts = [c - pos for c in (start, start + length) if pos + QTY < c < pos + size - QTY]
        edges = [0.0, *cuts, size]
        for a, b in zip(edges, edges[1:]):
            out.append([sign * (b - a), price])
        pos += size
    first = last = None
    pos = 0.0
    for i, (qty, _) in enumerate(out):
        if abs(pos - start) < QTY:
            first = i
        pos += abs(qty)
        if abs(pos - (start + length)) < QTY:
            last = i
    return out, first, last


class Calibrator:
    def __init__(self, backoffice):
        self.bo = backoffice

    def calibrate(self, content, filename):
        report = parse_pnl_report(content, filename)
        day = report["as_of"]
        if not day:
            raise OpeningPnlError("The report's date must be in the file name, e.g. MOP117_04-11-2026.XLS.")
        cf_as_of = max(self.bo.carry_forward.cutoffs().values(), default=None)
        if not cf_as_of or day <= cf_as_of:
            raise OpeningPnlError(f"Calibration is for days after the Carry Forward date ({cf_as_of}).")
        broker = {}
        for row in report["rows"]:
            exchange = exchange_for(row["underlying"])
            _, symbol = contract_id(exchange, row)
            key = contract_key({"symbol": symbol, "expiry": row["expiry"], "strike": row["strike"],
                                "option_type": row["option_type"]}, exchange)
            broker[key] = row

        ledger = self.bo._ledger(ReportFilters(), upto=day)
        costs = self.bo.opening_pnl.costs(cf_as_of)
        stored = self.bo.opening_pnl.lots(cf_as_of)
        positions = {contract_key(p, p["exchange"]): p for p in self.bo.carry_forward.collection.find()}

        changed, unexplained = {}, []
        for key, entry in ledger.items():
            records = dict(entry["days"])
            row = broker.get(key)
            if day not in records and row is None:
                continue
            app = records[day]["realised_pnl"] if day in records else 0.0
            delta = (float(row["realised_pnl"]) if row else 0.0) - app
            if abs(delta) < 0.5:
                continue
            position = positions.get(key)
            if not entry.get("opening") or position is None:
                unexplained.append((key, round(delta, 2), "not a C/F contract"))
                continue
            # How much of the C/F was consumed before and on this day (C/F lots are the oldest).
            cf_qty = abs(position["qty"])
            used_before = used_today = 0.0
            for d, record in entry["days"]:
                if d <= cf_as_of or d > day:
                    continue
                opening = abs(record["opening_qty"])
                remaining_cf = max(0.0, cf_qty - used_before)
                opposite = record["sell_qty"] if record["opening_qty"] > 0 else record["buy_qty"]
                consumed = min(remaining_cf, opening, opposite) if record["opening_qty"] else 0.0
                if record.get("settled_qty"):
                    consumed = remaining_cf
                if d == day:
                    used_today = consumed
                else:
                    used_before += consumed
            if used_today < QTY:
                unexplained.append((key, round(delta, 2), "C/F not consumed this day"))
                continue
            ident = position["_id"]
            lots = [list(l) for l in (stored.get(ident) or
                                      [[position["qty"], costs.get(ident, position["value"]) / cf_qty]])]
            lots, first, last = _split(lots, used_before, used_today)
            if first is None or last is None:
                unexplained.append((key, round(delta, 2), "could not locate the consumed lot"))
                continue
            segment = sum(abs(q) * p for q, p in lots[first:last + 1])
            long_position = position["qty"] > 0
            target = segment - delta if long_position else segment + delta
            rest = lots[last + 1:]
            if not rest or target < -0.01:
                unexplained.append((key, round(delta, 2), "no remaining C/F lot to carry the difference"))
                continue
            for i in range(first, last + 1):
                lots[i][1] = target / used_today
            rest_qty = abs(rest[0][0])  # compensate on the remainder of the same (oldest) lot
            new_rest = abs(rest[0][0]) * rest[0][1] + (segment - target)
            if new_rest < -0.01:
                unexplained.append((key, round(delta, 2), "difference larger than the remaining lot cost"))
                continue
            lots[last + 1][1] = new_rest / rest_qty
            merged = []
            for qty, price in lots:  # merge neighbours with the same price
                if merged and abs(merged[-1][1] - price) < 1e-9 and (merged[-1][0] > 0) == (qty > 0):
                    merged[-1][0] += qty
                else:
                    merged.append([qty, price])
            stored[ident] = merged
            changed[ident] = round(delta, 2)

        if changed:
            source = f"calibrated with broker P&L up to {day}"
            self.bo.opening_pnl.save_lots(cf_as_of, stored, source)
        # Re-check the day after calibration.
        ledger = self.bo._ledger(ReportFilters(), upto=day)
        remaining = []
        for key, row in broker.items():
            entry = ledger.get(key)
            app = dict(entry["days"]).get(day, {}).get("realised_pnl", 0.0) if entry else 0.0
            if abs(float(row["realised_pnl"]) - app) > 1:
                remaining.append((key, round(float(row["realised_pnl"]) - app, 2)))
        return {"date": day, "calibrated_contracts": len(changed), "adjustments": changed,
                "unexplained": unexplained, "still_different": remaining,
                "broker_realised": float(report["totals"]["realised_pnl"])}
