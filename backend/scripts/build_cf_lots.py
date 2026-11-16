r"""Split the Carry Forward into FIFO day-lots using the trades of the C/F date.

The broker closes a carried position oldest lot first. The C/F report gives one
average cost per contract; the trades of the C/F date show what the position
added that day. Under the broker's day-lot method that addition is the newest
lot (at the day's average price of that side), and the rest of the position is
the older lot at the remaining cost.

Usage (from backend):  .venv\Scripts\python scripts\build_cf_lots.py data\backups\nse_trades_2026-10-30.jsonl data\backups\bse_trades_2026-10-30.jsonl
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bson import json_util  # noqa: E402

from app.backoffice import normalize_strike  # noqa: E402
from app.database import MongoStore  # noqa: E402


def main(paths):
    day_totals = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    dates = set()
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                d = json_util.loads(line)
                dates.add(d["trade_date"])
                key = (d["exchange"], d["symbol"], d["expiry"], normalize_strike(d["strike"]), d["option_type"])
                qty, price = float(d["trade_quantity"]), float(d["trade_price"])
                t = day_totals[key]
                if str(d["buy_sell"]) == "1":
                    t[0] += qty; t[1] += qty * price
                else:
                    t[2] += qty; t[3] += qty * price
    if len(dates) != 1:
        raise SystemExit(f"Trades must be from one date, found {sorted(dates)}")
    as_of = dates.pop()
    store = MongoStore()
    try:
        lots_by_id = {}
        for row in store.db.opening_pnl.find({"as_of": as_of, "unrealised_qty": {"$ne": 0}}):
            qty, total = row["unrealised_qty"], row["cost_value"]
            key = (row["exchange"], row["symbol"], row["expiry"], normalize_strike(row["strike"]), row["option_type"])
            bq, bv, sq, sv = day_totals.get(key, (0, 0, 0, 0))
            added = (bq - sq) if qty > 0 else (sq - bq)
            if added <= 0:
                continue  # nothing added on the C/F date: one lot at the average cost
            added = min(added, abs(qty))
            price = bv / bq if qty > 0 else sv / sq
            sign = 1 if qty > 0 else -1
            older = abs(qty) - added
            lots = ([[sign * older, (total - added * price) / older]] if older > 1e-9 else []) + [[sign * added, price]]
            lots_by_id[row["_id"]] = lots
        print(store.backoffice.opening_pnl.save_lots(as_of, lots_by_id, f"trades of {as_of}"))
    finally:
        store.close()


if __name__ == "__main__":
    main(sys.argv[1:])
