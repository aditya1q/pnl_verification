"""Broker daily net position report -> official closing rates used as LTP."""
import unittest
import uuid
from pathlib import Path

from app.backoffice import ReportFilters
from app.closing_rates import ClosingRateError, parse_report
from app.database import MongoStore
from test_carry_forward import report_text

XLS = Path(__file__).resolve().parents[1] / "data" / "closing_rates" / "NETPOSS02112026_FO_B-117.xls"


class ParseXlsTests(unittest.TestCase):
    @unittest.skipUnless(XLS.exists(), "broker .xls sample not present")
    def test_real_xls_report(self):
        report = parse_report(XLS.read_bytes(), XLS.name)
        self.assertEqual((report["as_of"], report["client"], len(report["rows"])), ("2026-11-02", "MOP117 / NCR1", 259))
        self.assertEqual(report["totals"], {"buy_qty": 9636320, "buy_value": 180352955.5,
                                            "sell_qty": 9661195, "sell_value": 173953123.0})
        rows = {(r["underlying"], r["expiry"], r["strike"], r["option_type"]): r for r in report["rows"]}
        self.assertEqual(float(rows[("NIFTY", "03 NOV 2026", 23300, "PE")]["close_rate"]), 62.65)
        self.assertEqual(float(rows[("SENSEX", "05 NOV 2026", 73300, "PE")]["close_rate"]), 48.25)


    @unittest.skipUnless(XLS.exists() and XLS.with_suffix(".csv").exists(), "broker samples not present")
    def test_csv_report_matches_xls(self):
        csv_report = parse_report(XLS.with_suffix(".csv").read_bytes(), "NETPOSS02112026_FO_B-117.csv")
        xls_report = parse_report(XLS.read_bytes(), XLS.name)
        self.assertEqual((csv_report["as_of"], csv_report["client"], csv_report["totals"]),
                         (xls_report["as_of"], xls_report["client"], xls_report["totals"]))
        strip = lambda rows: [{k: v for k, v in r.items() if k != "line"} for r in rows]
        self.assertEqual(strip(csv_report["rows"]), strip(xls_report["rows"]))

    def test_csv_row_must_add_up(self):
        import csv, io
        rows = list(csv.reader(io.StringIO(XLS.with_suffix(".csv").read_text(encoding="utf-8-sig"))))
        first = next(i for i, r in enumerate(rows) if r and r[0] == "*")
        rows[first][10] = str(int(float(rows[first][10])) + 1)  # Net Qty off by one
        out = io.StringIO()
        csv.writer(out, lineterminator=chr(10)).writerows(rows)
        with self.assertRaisesRegex(ClosingRateError, "Net Qty"):
            parse_report(out.getvalue().encode(), "bad.csv")

    def test_excel_style_expiry_dates(self):
        import csv, io
        rows = list(csv.reader(io.StringIO(XLS.with_suffix(".csv").read_text(encoding="utf-8-sig"))))
        for row in rows:
            if row and row[0] == "*":
                day, month, year = row[3].replace("/", "-").split("-")
                row[3] = f"{int(day)}/{int(month)}/{year}"  # 03-11-2026 -> 3/11/2026
        out = io.StringIO()
        csv.writer(out, lineterminator=chr(10)).writerows(rows)
        report = parse_report(out.getvalue().encode(), "excel.csv")
        self.assertIn("03 NOV 2026", {r["expiry"] for r in report["rows"]})
        self.assertEqual(len(report["rows"]), 259)


class ClosingRateMongoTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore(database=f"cr_test_{uuid.uuid4().hex[:10]}")
        try:
            self.store.ping()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.store.close()
            self.skipTest(f"MongoDB not available: {exc}")
        self.store.indexes()
        # C/F 30 Oct: long 10 of 23500 CE (close 100), short 5 of 23600 CE (close 50, never trades).
        self.store.backoffice.carry_forward.import_report(
            report_text([(23500, "CE", 10, 1000, 0, 0, 100), (23600, "CE", 0, 0, 5, 250, 50)]), "cf.txt")
        self.bo = self.store.backoffice

    def tearDown(self):
        self.store.client.drop_database(self.store.db.name)
        self.store.close()

    def test_close_rate_marks_open_position(self):
        s = self.bo.summary(ReportFilters())
        self.assertEqual((s["as_of"], s["unrealized_pnl"], s["open_positions"]), ("2026-10-30", 0.0, 2))
        result = self.bo.closing_rates.import_report(
            report_text([(23500, "CE", 0, 0, 6, 660, 120)], as_on="02/11/2026").encode(), "netpos.txt")
        self.assertEqual((result["date"], result["contracts"], result["closing_rates"]), ("2026-11-02", 1, 1))
        s = self.bo.summary(ReportFilters())
        # Realized 6 x (110 - 100); unrealized 4 x (120 - 100) at the official close.
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"], s["mtm_pnl"]), (60.0, 80.0, 140.0))
        self.assertEqual((s["buy_value"], s["sell_value"], s["net_value"], s["stale_ltp"]), (0.0, 660.0, 660.0, 1))
        pos = {r["strike"]: r for r in self.bo.position_rows(ReportFilters())["rows"]}
        self.assertEqual((pos[23500]["ltp"], pos[23500]["ltp_source"]), (120.0, "BROKER_CLOSE"))
        # Re-import is idempotent.
        self.bo.closing_rates.import_report(
            report_text([(23500, "CE", 0, 0, 6, 660, 120)], as_on="02/11/2026").encode(), "netpos.txt")
        self.assertEqual((self.store.db.market_prices.count_documents({}),
                          self.store.db.net_positions.count_documents({})), (1, 1))

    def test_report_on_cf_date_rejected(self):
        with self.assertRaisesRegex(ClosingRateError, "on or before the Carry Forward date"):
            self.bo.closing_rates.import_report(
                report_text([(23500, "CE", 0, 0, 7, 770, 120)], as_on="30/10/2026").encode(), "netpos.txt")
        self.assertEqual(self.store.db.net_positions.count_documents({}), 0)

    @unittest.skipUnless(XLS.with_suffix(".csv").exists(), "broker .csv sample not present")
    def test_day_view_keeps_every_report_column(self):
        csv = XLS.with_suffix(".csv")
        store = MongoStore(database=f"cr_view_{uuid.uuid4().hex[:10]}")
        try:
            store.indexes()
            store.backoffice.closing_rates.import_report(csv.read_bytes(), csv.name)
            view = store.backoffice.closing_rates.rows("NSE", "2026-11-02", limit=500)
            self.assertEqual(view["total"], 165)
            self.assertEqual((view["totals"]["buy_value"], view["totals"]["sell_value"], view["totals"]["net_value"]),
                             (156461454.5, 144221467, -12239987.5))
            first = view["rows"][0]
            self.assertEqual((first["underlying"], first["strike"], first["option_type"], first["buy_qty"],
                              first["net_qty"], first["avg_rate"], first["close_rate"], first["mtm"],
                              first["report_exchange"], first["group"]),
                             ("NIFTY", 23000, "CE", 5850, 5850, 302.89, 339.8, -1771916.25, "NFO", "*"))
            found = store.backoffice.closing_rates.rows("BSE", "2026-11-02", search="73300")
            self.assertEqual([(r["strike"], r["option_type"]) for r in found["rows"]], [(73300, "PE")])
        finally:
            store.client.drop_database(store.db.name)
            store.close()


class NetPositionOnlyTests(unittest.TestCase):
    """No trade files at all: each day comes from the broker's net position report."""

    def setUp(self):
        self.store = MongoStore(database=f"np_test_{uuid.uuid4().hex[:10]}")
        try:
            self.store.ping()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.store.close()
            self.skipTest(f"MongoDB not available: {exc}")
        self.store.indexes()
        self.bo = self.store.backoffice
        # C/F 30 Oct (Friday): long 10 of 23500 CE @ 100.
        self.bo.carry_forward.import_report(report_text([(23500, "CE", 10, 1000, 0, 0, 100)]), "cf.txt")

    def tearDown(self):
        self.store.client.drop_database(self.store.db.name)
        self.store.close()

    def day(self, as_on, rows):
        return self.bo.closing_rates.import_report(report_text(rows, as_on=as_on).encode(), f"np{as_on[:2]}.txt")

    def test_day_and_month_pnl_from_reports(self):
        # 2 Nov: sell 6 @ 110, buy 20 @ 10 / sell 20 @ 12 of 23600 CE (closes 13). 23500 closes 120.
        first = self.day("02/11/2026", [(23500, "CE", 0, 0, 6, 660, 120), (23600, "CE", 20, 200, 20, 240, 13)])
        self.assertEqual((first["contracts"], first["missing_days"]), (2, {}))
        # 4 Nov (3 Nov skipped): sell the other 4 @ 90.
        second = self.day("04/11/2026", [(23500, "CE", 0, 0, 4, 360, 90)])
        self.assertEqual(second["missing_days"], {"NSE": ["2026-11-03"]})

        days = {r["date"]: r for r in self.bo.daily(ReportFilters())["rows"]}
        self.assertEqual(sorted(days), ["2026-11-02", "2026-11-04"])
        d1, d2 = days["2026-11-02"], days["2026-11-04"]
        # Day 1: realized 6 x 10 + 20 x 2 = 100; unrealized 4 x (120 - 100) = 80.
        self.assertEqual((d1["realized_pnl"], d1["unrealized_pnl"], d1["mtm_pnl"]), (100.0, 80.0, 180.0))
        self.assertEqual((d1["buy_value"], d1["sell_value"], d1["net_value"]), (200.0, 900.0, 700.0))
        # Day 2: realized 4 x (90 - 100) = -40; unrealized 0; MTM -40 - 80 = -120.
        self.assertEqual((d2["realized_pnl"], d2["unrealized_pnl"], d2["mtm_pnl"]), (-40.0, 0.0, -120.0))
        month = self.bo.monthly(ReportFilters())["rows"][0]
        self.assertEqual((month["realized_pnl"], month["unrealized_pnl"], month["mtm_pnl"], month["trading_days"]),
                         (60.0, 0.0, 60.0, 2))
        s = self.bo.summary(ReportFilters())
        self.assertEqual((s["as_of"], s["realized_pnl"], s["open_positions"]), ("2026-11-04", 60.0, 0))

        options = self.bo.filter_options()
        self.assertEqual((options["first_date"], options["last_date"]), ("2026-11-02", "2026-11-04"))
        # Re-import replaces the day.
        self.day("04/11/2026", [(23500, "CE", 0, 0, 4, 360, 90)])
        self.assertEqual(self.store.db.net_positions.count_documents({}), 3)
        self.assertEqual(self.bo.summary(ReportFilters())["realized_pnl"], 60.0)


if __name__ == "__main__":
    unittest.main()
