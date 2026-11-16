import unittest

from app.broker_pnl import apply_day


class ApplyDayTests(unittest.TestCase):
    def test_broker_file_row_without_opening(self):
        # NIFTY 03 NOV 2026 21450 PE on 30 Oct (broker file, account MOP117).
        r = apply_day(0, 0.0, 25740, 54340.0, 26780, 45812.0)
        self.assertAlmostEqual(r["realised_pnl"], -10307.11, places=2)
        self.assertEqual(r["realised_qty"], 25740)
        self.assertAlmostEqual(r["realised_buy_value"], 54340.00, places=2)
        self.assertAlmostEqual(r["realised_sell_value"], 44032.89, places=2)
        self.assertEqual(r["closing_qty"], -1040)
        self.assertAlmostEqual(r["closing_value"], 1779.11, places=2)

    def test_opening_long_squares_off_first_at_day_average_sell(self):
        # Opening long 50 @ 9; day: buy 100 @ 10, sell 40 @ 12.
        r = apply_day(50, 450.0, 100, 1000.0, 40, 480.0)
        self.assertAlmostEqual(r["realised_pnl"], 40 * (12 - 9))
        self.assertEqual((r["realised_qty"], r["closing_qty"]), (40, 110))
        self.assertAlmostEqual(r["closing_value"], 10 * 9 + 1000)  # rest of opening + day buys

    def test_opening_short_then_day_average(self):
        # Opening short 10 @ 20; day: buy 30 @ 15 (avg), sell 5 @ 18.
        r = apply_day(-10, 200.0, 30, 450.0, 5, 90.0)
        # 10 bought back at the day's avg buy 15 -> +50; then 5 of the remaining 20 buys match the 5 sells: 5 x (18 - 15) = +15
        self.assertAlmostEqual(r["realised_pnl"], 65.0)
        self.assertEqual((r["realised_qty"], r["closing_qty"]), (15, 15))
        self.assertAlmostEqual(r["closing_value"], 15 * 15)

    def test_opening_larger_than_opposite_side_keeps_blended_cost(self):
        # Opening long 100 @ 10, sell 30 @ 12, buy 50 @ 14: 30 close against opening, 70 @10 + 50 @14 stay open.
        r = apply_day(100, 1000.0, 50, 700.0, 30, 360.0)
        self.assertAlmostEqual(r["realised_pnl"], 30 * 2)
        self.assertEqual(r["closing_qty"], 120)
        self.assertAlmostEqual(r["closing_value"], 700 + 700)

    def test_flat_day(self):
        r = apply_day(0, 0.0, 10, 1000.0, 10, 1000.0)
        self.assertEqual((r["realised_pnl"], r["closing_qty"], r["closing_value"]), (0.0, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
