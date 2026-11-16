"""FIFO day-lots, bhavcopy closing rates and expiry settlement."""
import unittest
import uuid

from app.backoffice import ReportFilters
from app.bhavcopy import parse_bhavcopy, settlement_value
from app.broker_pnl import apply_day_lots, settle_lots
from app.database import MongoStore
from test_carry_forward import report_text

HEADER = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,"
          "OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric")


def bhav(day, rows):
    """rows: (expiry ISO, strike, CE/PE, close, settle, underlying price)."""
    lines = [HEADER]
    for expiry, strike, opt, close, settle, under in rows:
        lines.append(f"{day},{day},FO,NSE,IDO,1,,NIFTY,,{expiry},{expiry},{strike}.00,{opt},X,0,0,0,{close},{close},0,"
                     f"{under},{settle}")
    return ("\n".join(lines) + "\n").encode()


class LotTests(unittest.TestCase):
    def test_fifo_oldest_lot_first(self):
        r = apply_day_lots([[10, 100.0], [10, 120.0]], 0, 0.0, 15, 15 * 130.0)
        self.assertEqual((r["realised_pnl"], r["realised_qty"], r["closing_lots"]), (10 * 30 + 5 * 10, 15, [[5, 120.0]]))

    def test_short_lots_and_new_lot(self):
        r = apply_day_lots([[-5, 50.0]], 8, 8 * 40.0, 2, 2 * 45.0)
        # 5 bought back at avg 40 (+50), then 2 buy vs 2 sell at average (+10), 1 long left at 40.
        self.assertEqual((r["realised_pnl"], r["closing_lots"]), (5 * 10 + 2 * 5, [[1, 40.0]]))

    def test_settlement(self):
        r = settle_lots([[10, 100.0], [-0, 0]], 130.0)
        self.assertEqual((r["realised_pnl"], r["closing_qty"]), (300.0, 0))
        self.assertEqual(settlement_value({"option_type": "CE", "strike": 23000, "settle": 23810.85}), 810.85)
        self.assertEqual(settlement_value({"option_type": "PE", "strike": 23000, "settle": 23810.85}), 0.0)

    def test_parse(self):
        report = parse_bhavcopy(bhav("2026-11-02", [("2026-11-03", 23500, "CE", 21.15, 21.15, 23400)]))
        row = report["rows"][0]
        self.assertEqual((report["date"], row["symbol"], row["expiry"], row["strike"], row["close"]),
                         ("2026-11-02", "NIFTY03NOVOPT", "03 NOV 2026", 23500, 21.15))


class BhavcopyMongoTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore(database=f"bh_test_{uuid.uuid4().hex[:10]}")
        try:
            self.store.ping()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.store.close()
            self.skipTest(f"MongoDB not available: {exc}")
        self.store.indexes()
        self.bo = self.store.backoffice
        # C/F 30 Oct: long 10 of 23500 CE @ 100 (expires 3 Nov), short 5 of 23600 CE @ 50.
        self.bo.carry_forward.import_report(
            report_text([(23500, "CE", 10, 1000, 0, 0, 100), (23600, "CE", 0, 0, 5, 250, 50)]), "cf.txt")
        # 2 Nov: only 23500 CE trades (sell 4 @ 110, close 110). 23600 CE is not in the report.
        self.bo.closing_rates.import_report(
            report_text([(23500, "CE", 0, 0, 4, 440, 110)], as_on="02/11/2026").encode(), "np02.txt")

    def tearDown(self):
        self.store.client.drop_database(self.store.db.name)
        self.store.close()

    def test_close_for_untraded_and_expiry_settlement(self):
        before = self.bo.summary(ReportFilters())
        self.assertEqual((before["unrealized_pnl"], before["stale_ltp"]), (60.0, 1))  # 6 x 10; 23600 on C/F close
        self.bo.bhavcopy.import_file(bhav("2026-11-02", [("2026-11-03", 23500, "CE", 999, 999, 23400),
                                                          ("2026-11-03", 23600, "CE", 40, 40, 23400)]),
                                     "BhavCopy_NSE_FO_0_0_0_20261102_F_0000.csv")
        s = self.bo.summary(ReportFilters())
        # 23500 keeps the broker close 110 (not overwritten); 23600 short marked to 40: 5 x (50 - 40) = 50.
        self.assertEqual((s["unrealized_pnl"], s["stale_ltp"]), (60.0 + 50.0, 0))
        # 3 Nov expiry, no trades: index settles at 23540 -> 23500 CE = 40, 23600 CE = 0.
        self.bo.bhavcopy.import_file(bhav("2026-11-03", [("2026-11-03", 23500, "CE", 41, 23540, 23540),
                                                          ("2026-11-03", 23600, "CE", 1, 23540, 23540)]),
                                     "BhavCopy_NSE_FO_0_0_0_20261103_F_0000.csv")
        days = {r["date"]: r for r in self.bo.daily(ReportFilters(date_to="2026-11-03"))["rows"]}
        s = self.bo.summary(ReportFilters(date_to="2026-11-03"))
        # Realised: 2 Nov 4 x 10 = 40; 3 Nov settlement 6 x (40 - 100) + 5 x (50 - 0) = -110. Nothing left open.
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"], s["open_positions"]), (40.0 - 110.0, 0.0, 0))


if __name__ == "__main__":
    unittest.main()
