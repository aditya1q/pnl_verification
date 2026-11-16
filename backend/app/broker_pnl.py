"""Broker (RMS) P&L method, verified contract by contract against the broker's
"NSE FO Realised & Unrealised" report for account MOP117 (2 Nov 2026):

- All terminals of the account are pooled per contract.
- Each day's buys are one lot at the day's average buy price, and its sells one
  lot at the day's average sell price.
- An open position is a FIFO queue of such day-lots (oldest first). The day's
  opposite side squares off the open lots first, oldest lot first, at the day's
  average opposite price.
- The rest of the day's buys and sells are matched at their average prices:
  realised qty = min(buy qty, sell qty), realised P&L = qty x (avg sell - avg buy).
- What is left of the day joins the queue as a new lot at its average price.
- On expiry day, whatever is still open is settled at the settlement price
  (``settle_lots``) and realised.

Values are price x quantity (option/future quantities are already in units).
"""
from __future__ import annotations

QTY_TOLERANCE = 1e-6


def _result(realised, realised_qty, realised_buy, realised_sell, lots):
    lots = [[q, p] for q, p in lots if abs(q) > QTY_TOLERANCE]
    closing_qty = sum(q for q, _ in lots)
    closing_value = sum(abs(q) * p for q, p in lots)
    if abs(closing_qty) < QTY_TOLERANCE:
        closing_qty, closing_value, lots = 0, 0.0, []
    return {
        "realised_pnl": realised, "realised_qty": realised_qty,
        "realised_buy_value": realised_buy, "realised_sell_value": realised_sell,
        "closing_qty": closing_qty, "closing_value": closing_value, "closing_lots": lots,
    }


def apply_day_lots(lots, buy_qty, buy_value, sell_qty, sell_value):
    """One trading day for one contract.

    ``lots`` is the open position: [[signed qty, price], ...] oldest first, all on
    one side (+ long / - short). Returns realised P&L, realised qty, realised
    buy / sell value and the closing lots (with their total qty and cost value).
    """
    realised = realised_qty = realised_buy = realised_sell = 0.0
    lots = [[q, p] for q, p in lots if abs(q) > QTY_TOLERANCE]
    bq, bv, sq, sv = buy_qty, buy_value, sell_qty, sell_value
    avg_buy = bv / bq if bq else 0.0
    avg_sell = sv / sq if sq else 0.0

    # 1. Carried lots square off first, oldest first, at the day's average opposite price.
    long_open = bool(lots) and lots[0][0] > 0
    while lots and ((long_open and sq > QTY_TOLERANCE) or (not long_open and bq > QTY_TOLERANCE)):
        qty, price = lots[0]
        if long_open:
            close = min(qty, sq)
            realised += close * (avg_sell - price)
            realised_buy += close * price
            realised_sell += close * avg_sell
            sq -= close
            lots[0][0] -= close
        else:
            close = min(-qty, bq)
            realised += close * (price - avg_buy)
            realised_buy += close * avg_buy
            realised_sell += close * price
            bq -= close
            lots[0][0] += close
        realised_qty += close
        if abs(lots[0][0]) < QTY_TOLERANCE:
            lots.pop(0)

    # 2. Remaining day trades: average-price matching.
    matched = min(bq, sq)
    if matched > QTY_TOLERANCE:
        realised += matched * (avg_sell - avg_buy)
        realised_buy += matched * avg_buy
        realised_sell += matched * avg_sell
        realised_qty += matched
        bq -= matched
        sq -= matched

    # 3. What is left of the day (one side only) becomes the newest lot.
    if bq > QTY_TOLERANCE:
        lots.append([bq, avg_buy])
    elif sq > QTY_TOLERANCE:
        lots.append([-sq, avg_sell])
    return _result(realised, realised_qty, realised_buy, realised_sell, lots)


def settle_lots(lots, price):
    """Expiry: every open lot is closed at the settlement ``price`` and realised."""
    realised = realised_qty = realised_buy = realised_sell = 0.0
    for qty, cost in lots:
        if qty > 0:
            realised += qty * (price - cost)
            realised_buy += qty * cost
            realised_sell += qty * price
        else:
            realised += -qty * (cost - price)
            realised_buy += -qty * price
            realised_sell += -qty * cost
        realised_qty += abs(qty)
    return _result(realised, realised_qty, realised_buy, realised_sell, [])


def apply_day(open_qty, open_value, buy_qty, buy_value, sell_qty, sell_value):
    """Single-lot form of ``apply_day_lots``: the open position is one lot at its average cost."""
    lots = [[open_qty, open_value / abs(open_qty)]] if open_qty else []
    return apply_day_lots(lots, buy_qty, buy_value, sell_qty, sell_value)
