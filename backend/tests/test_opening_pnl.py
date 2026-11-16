"""Broker P&L report as on the C/F date: original cost basis and cumulative P&L."""
import unittest
import uuid
from pathlib import Path

from app.backoffice import ReportFilters
from app.database import MongoStore
from app.opening_pnl import OpeningPnlError, parse_pnl_report
from test_carry_forward import report_text

DATA = Path(__file__).resolve().parents[1] / "data" / "carry_forward"
REAL = DATA / "MOP117_30-10-2026.csv"
HEADER = ("Client Code,Security Name,Option Type,Strike Price,Realised Qty,Realised Buy Value,Realised Sell Value,"
          "Realised P&L,Unrealised Qty,Unrealised Buy Value,Unrealised Sell Value,Unrealised Value,Close Rate,"
          "Close Value,Unrealised P&L With CloseRate,Unrealised P&L,Realised+Unrealised,MTM")


def pnl_csv(rows):
    """rows: (strike, opt, realised qty, realised buy, realised sell, open qty, open buy, open sell, close)."""
    lines, totals = [HEADER], [0.0] * 14
    for strike, opt, rq, rb, rs, uq, ub, us, close in rows:
        rp, uv = rs - rb, us - ub
        cv = uq * close
        uc = cv + uv
        values = [rq, rb, rs, rp, uq, ub, us, uv, close, cv, uc, uv, rp + uv, rp + uc]
        lines.append(",".join(["MOP117", "OPTIDXNIFTY03NOV2026", opt, f'"{strike:,.2f}"'] + [f'"{v:,.2f}"' for v in values]))
        totals = [t + v for t, v in zip(totals, values)]
    totals[8] = 0
    lines.append(",".join(["TOTALS", "", "", ""] + [f'"{v:,.2f}"' if i != 8 else "" for i, v in enumerate(totals)]))
    lines.append(",,,,,,,,,,,,,,,TOTAL CHRGES,\"-10.00\",")
    return "\n".join(lines) + "\n"


class ParsePnlTests(unittest.TestCase):
    @unittest.skipUnless(REAL.exists(), "broker P&L sample not present")
    def test_real_report(self):
        report = parse_pnl_report(REAL.read_bytes(), REAL.name)
        self.assertEqual((report["as_of"], report["client"], len(report["rows"])), ("2026-10-30", "MOP117", 239))
        self.assertEqual((float(report["totals"]["realised_pnl"]), float(report["totals"]["unrealised_pnl_close"]),
                          float(report["totals"]["mtm"])), (-2271392.55, 1553921.46, -717471.09))
        self.assertEqual((report["charges"]["TOTAL CHRGES"], report["charges"]["NET MTM"]), (-405827.29, -1123298.38))
        fut = report["rows"][0]
        self.assertEqual((fut["instrument_name"], fut["underlying"], fut["expiry"], fut["option_type"], fut["strike"]),
                         ("FUTIDX", "NIFTY", "23 NOV 2026", "FX", 0))

    def test_row_must_add_up(self):
        text = pnl_csv([(23500, "CE", 10, 1000, 1100, 4, 400, 0, 120)]).replace('"100.00","4.00"', '"110.00","4.00"')
        with self.assertRaisesRegex(OpeningPnlError, "does not add up"):
            parse_pnl_report(text, "MOP117_30-10-2026.csv")


class OpeningPnlMongoTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore(database=f"op_test_{uuid.uuid4().hex[:10]}")
        try:
            self.store.ping()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.store.close()
            self.skipTest(f"MongoDB not available: {exc}")
        self.store.indexes()
        self.bo = self.store.backoffice
        # C/F 30 Oct: long 10 of 23500 CE, close 100. The broker bought them at 80 (cost 800).
        self.bo.carry_forward.import_report(report_text([(23500, "CE", 10, 800, 0, 0, 100)]), "cf.txt")
        # 2 Nov: sell 6 @ 110, close 110.
        self.bo.closing_rates.import_report(
            report_text([(23500, "CE", 0, 0, 6, 660, 110)], as_on="02/11/2026").encode(), "np02.txt")

    def tearDown(self):
        self.store.client.drop_database(self.store.db.name)
        self.store.close()

    def test_original_cost_and_cumulative(self):
        before = self.bo.summary(ReportFilters())
        self.assertEqual((before["realized_pnl"], before["unrealized_pnl"], before["mtm_pnl"]), (60.0, 40.0, 100.0))
        self.assertIsNone(before["cumulative"])
        # Till 30 Oct: realised 50 on another contract; open 10 @ 80 -> unrealised 10 x (100 - 80) = 200.
        text = pnl_csv([(23500, "CE", 0, 0, 0, 10, 800, 0, 100), (23600, "CE", 5, 500, 550, 0, 0, 0, 40)])
        result = self.bo.opening_pnl.import_report(text, "MOP117_30-10-2026.csv")
        self.assertEqual((result["realised_pnl"], result["unrealised_pnl"], result["open_positions"]), (50.0, 200.0, 1))
        s = self.bo.summary(ReportFilters())
        # Realized 6 x (110 - 80) = 180; unrealized 4 x (110 - 80) = 120; day MTM unchanged = 180 + 120 - 200.
        self.assertEqual((s["cost_basis"], s["realized_pnl"], s["unrealized_pnl"], s["mtm_pnl"]),
                         ("BROKER_COST", 180.0, 120.0, 100.0))
        self.assertEqual(s["cumulative"], {"realized_pnl": 230.0, "unrealized_pnl": 120.0, "total_pnl": 350.0})
        self.assertEqual(s["opening_pnl"]["total_pnl"], 250.0)
        day = self.bo.daily(ReportFilters())["rows"][0]
        self.assertEqual((day["realized_pnl"], day["previous_unrealized_pnl"], day["mtm_pnl"]), (180.0, 200.0, 100.0))
        pos = self.bo.position_rows(ReportFilters())["rows"][0]
        self.assertEqual((pos["open_qty"], pos["avg_price"]), (4, 80.0))
        # Re-importing the C/F keeps the broker cost (looked up, not copied).
        self.bo.carry_forward.import_report(report_text([(23500, "CE", 10, 800, 0, 0, 100)]), "cf.txt")
        self.assertEqual(self.bo.summary(ReportFilters())["realized_pnl"], 180.0)

    def test_cf_lots_close_oldest_first(self):
        text = pnl_csv([(23500, "CE", 0, 0, 0, 10, 800, 0, 100)])
        self.bo.opening_pnl.import_report(text, "MOP117_30-10-2026.csv")
        ident = "NSE|NIFTY03NOVOPT|03 NOV 2026|23500|CE"
        # 10 @ 80 = 4 bought earlier @ 50 + 6 bought on the C/F date @ 100.
        with self.assertRaisesRegex(OpeningPnlError, "lot problem"):
            self.bo.opening_pnl.save_lots("2026-10-30", {ident: [[4, 50.0], [6, 99.0]]}, "test")
        self.bo.opening_pnl.save_lots("2026-10-30", {ident: [[4, 50.0], [6, 100.0]]}, "test")
        s = self.bo.summary(ReportFilters())
        # 2 Nov sells 6 @ 110: 4 x (110 - 50) + 2 x (110 - 100) = 260; 4 left @ 100 -> 4 x (110 - 100) = 40.
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"], s["mtm_pnl"]), (260.0, 40.0, 100.0))

    def test_calibration_with_broker_report(self):
        from app.calibration import Calibrator
        self.bo.opening_pnl.import_report(pnl_csv([(23500, "CE", 0, 0, 0, 10, 800, 0, 100)]), "MOP117_30-10-2026.csv")
        self.assertEqual(self.bo.summary(ReportFilters())["realized_pnl"], 180.0)  # 6 x (110 - 80)
        # Broker 2 Nov: the 6 sold were its oldest lot at 75 -> realised 6 x (110 - 75) = 210;
        # the remaining 4 cost 800 - 450 = 350 -> unrealised 4 x (110 - 87.5) = 90.
        broker = pnl_csv([(23500, "CE", 6, 450, 660, 4, 350, 0, 110)])
        result = Calibrator(self.bo).calibrate(broker, "MOP117_02-11-2026.csv")
        self.assertEqual((result["calibrated_contracts"], result["still_different"]), (1, []))
        s = self.bo.summary(ReportFilters())
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"], s["mtm_pnl"]), (210.0, 90.0, 100.0))
        again = Calibrator(self.bo).calibrate(broker, "MOP117_02-11-2026.csv")
        self.assertEqual(again["calibrated_contracts"], 0)  # idempotent

    def test_report_must_match_carry_forward(self):
        with self.assertRaisesRegex(OpeningPnlError, "Carry Forward Net Qty 10"):
            self.bo.opening_pnl.import_report(pnl_csv([(23500, "CE", 0, 0, 0, 9, 720, 0, 100)]),
                                              "MOP117_30-10-2026.csv")
        with self.assertRaisesRegex(OpeningPnlError, "Carry Forward is as of 2026-10-30"):
            self.bo.opening_pnl.import_report(pnl_csv([(23500, "CE", 0, 0, 0, 10, 800, 0, 100)]),
                                              "MOP117_29-10-2026.csv")
        self.assertIsNone(self.bo.opening_pnl.summary())


if __name__ == "__main__":
    unittest.main()
