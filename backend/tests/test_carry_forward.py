"""Carry Forward (C/F) import and month-to-month P&L from the C/F opening."""
import unittest
import uuid
from pathlib import Path

from app.backoffice import ReportFilters
from app.carry_forward import CarryForwardError, parse_net_position, to_positions
from app.database import MongoStore

REPORT = Path(__file__).resolve().parents[1] / "data" / "carry_forward" / "NFO_NETPOSITION_30102026.txt"


def report_text(rows, as_on="30/10/2026"):
    """A minimal broker net position report: rows are (strike, opt, buy_qty, buy_value, sell_qty, sell_value, close)."""
    lines = [f"   As On Date:{as_on}        Clos Date:{as_on}", "   MOP117           NCR1"]
    totals = [0, 0.0, 0, 0.0]
    for strike, opt, bq, bv, sq, sv, close in rows:
        net = bq - sq
        lines.append(f"   OPTIDX  NIFTY       03/11/26  {strike:.2f}  {opt}  {bq}  {bv:.2f}  {sq}  {sv:.2f}  "
                     f"{net}  {sv - bv:.2f}  0.00  {close:.2f}  0.00  0.00")
        totals = [totals[0] + bq, totals[1] + bv, totals[2] + sq, totals[3] + sv]
    lines.append(f"          Buy Value:   {totals[1]:.2f}   Sale  Value:   {totals[3]:.2f} Net Value:  0.00")
    lines.append(f"          Buy Qty:   {totals[0]}   Sale Qty:   {totals[2]} Net Qty:   {totals[0] - totals[2]}")
    return "\n".join(lines) + "\n"


class ParseReportTests(unittest.TestCase):
    def test_real_report_parses_and_adds_up(self):
        report = parse_net_position(REPORT.read_text())
        self.assertEqual((report["as_of"], report["client"], len(report["rows"])), ("2026-10-30", "MOP117 / NCR1", 190))
        self.assertEqual(report["totals"]["net_qty"], 102875)
        positions = {p["_id"]: p for p in to_positions(report)}
        self.assertEqual(len(positions), sum(1 for r in report["rows"] if r["net_qty"]))
        fut = positions["NSE|NIFTY23NOVFUT|23 NOV 2026|0|FX"]
        self.assertEqual((fut["qty"], fut["price"], fut["instrument_name"]), (67665, 23098.9, "FUTIDX"))
        short = positions["NSE|NIFTY03NOVOPT|03 NOV 2026|22000|PE"]
        self.assertEqual((short["qty"], short["price"], short["value"]), (-88270, 3.65, 88270 * 3.65))
        sensex = positions["BSE|SENSEX05NOVOPT|05 NOV 2026|73300|PE"]
        self.assertEqual((sensex["qty"], sensex["price"]), (-46180, 195.9))
        self.assertIn("NSE|NIFTY30MAROPT|30 MAR 2027|24000|CE", positions)

    def test_totals_must_match(self):
        text = REPORT.read_text().replace("Net Qty:                         102875", "Net Qty:                         102876")
        with self.assertRaisesRegex(CarryForwardError, "net_qty"):
            parse_net_position(text)

    def test_duplicate_contract_rejected(self):
        text = report_text([(23500, "CE", 10, 1000, 0, 0, 100), (23500, "CE", 10, 1000, 0, 0, 100)])
        with self.assertRaisesRegex(CarryForwardError, "duplicate"):
            parse_net_position(text)

    def test_unreadable_row_rejected(self):
        text = report_text([(23500, "CE", 10, 1000, 0, 0, 100)]).replace("03/11/26", "03-11-26")
        with self.assertRaisesRegex(CarryForwardError, "could not be read"):
            parse_net_position(text)


class CarryForwardMongoTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore(database=f"cf_test_{uuid.uuid4().hex[:10]}")
        try:
            self.store.ping()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.store.close()
            self.skipTest(f"MongoDB not available: {exc}")
        self.store.indexes()
        # C/F 30 Oct: long 10 of 23500 CE (close 100), short 5 of 23600 CE (close 50).
        self.text = report_text([(23500, "CE", 10, 1200, 0, 0, 100), (23600, "CE", 0, 0, 5, 200, 50)])
        result = self.store.backoffice.carry_forward.import_report(self.text, "cf.txt")
        self.assertEqual((result["open_positions"], result["as_of"]), (2, "2026-10-30"))
        self.bo = self.store.backoffice
        # 2 Nov net position: 6 of the C/F long sold @ 110, close 110. 23600 CE did not trade.
        self.bo.closing_rates.import_report(
            report_text([(23500, "CE", 0, 0, 6, 660, 110)], as_on="02/11/2026").encode(), "np02.txt")

    def tearDown(self):
        self.store.client.drop_database(self.store.db.name)
        self.store.close()

    def test_cf_is_opening_balance(self):
        s = self.bo.summary(ReportFilters())
        self.assertEqual((s["buy_qty"], s["sell_qty"], s["buy_value"], s["sell_value"]), (0, 6, 0.0, 660.0))
        # Realized: 6 x (110 - C/F close 100). Unrealized: 4 open x (close 110 - 100); 23600 CE at C/F close = 0.
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"], s["mtm_pnl"]), (60.0, 40.0, 100.0))
        # Opening value 10 x 100 - 5 x 50 = 750, reported on its own. Net Value is Sell - Buy: 660 - 0.
        self.assertEqual((s["opening_value"], s["trade_net_value"], s["net_value"]), (750.0, 660.0, 660.0))
        self.assertEqual((s["cf_as_of"], s["cycle_start"], s["as_of"]), ("2026-10-30", "2026-11-02", "2026-11-02"))

        positions = {r["strike"]: r for r in self.bo.position_rows(ReportFilters())["rows"]}
        self.assertEqual((positions[23500]["open_qty"], positions[23500]["avg_price"], positions[23500]["ltp_source"]),
                         (4, 100.0, "BROKER_CLOSE"))
        self.assertEqual((positions[23600]["side"], positions[23600]["ltp"], positions[23600]["ltp_source"],
                          positions[23600]["unrealized_pnl"]), ("SHORT", 50.0, "CF_CLOSE", 0.0))
        self.assertTrue(positions[23600]["carried_forward"])

    def test_day_and_month_rows(self):
        days = self.bo.daily(ReportFilters())["rows"]
        self.assertEqual([d["date"] for d in days], ["2026-11-02"])
        self.assertEqual((days[0]["realized_pnl"], days[0]["unrealized_pnl"], days[0]["mtm_pnl"]), (60.0, 40.0, 100.0))
        months = self.bo.monthly(ReportFilters())["rows"]
        self.assertEqual(len(months), 1)
        m = months[0]
        self.assertEqual((m["month"], m["trading_days"], m["opening_value"], m["net_value"]), ("2026-11", 1, 750.0, 660.0))
        self.assertEqual((m["realized_pnl"], m["unrealized_pnl"], m["mtm_pnl"]), (60.0, 40.0, 100.0))

    def test_manual_ltp_overrides_close_rate(self):
        self.bo.set_ltp("NSE", "NIFTY03NOVOPT", "03 NOV 2026", 23500, "CE", "2026-11-02", 90)
        s = self.bo.summary(ReportFilters())
        self.assertEqual((s["realized_pnl"], s["unrealized_pnl"]), (60.0, -40.0))  # 4 x (90 - 100)
        self.bo.clear_ltp("NSE", "NIFTY03NOVOPT", "03 NOV 2026", 23500, "CE", "2026-11-02")
        self.assertEqual(self.bo.summary(ReportFilters())["unrealized_pnl"], 40.0)

    def test_later_period_excludes_opening_value(self):
        s = self.bo.summary(ReportFilters(date_from="2026-11-03"))
        self.assertEqual((s["opening_included"], s["opening_value"], s["realized_pnl"]), (False, 0.0, 0.0))

    def test_reimport_replaces_instead_of_duplicating(self):
        self.bo.carry_forward.import_report(self.text, "cf.txt")
        self.assertEqual(self.store.db.carry_forward.count_documents({}), 2)
        self.assertEqual(self.bo.summary(ReportFilters())["realized_pnl"], 60.0)


if __name__ == "__main__":
    unittest.main()
