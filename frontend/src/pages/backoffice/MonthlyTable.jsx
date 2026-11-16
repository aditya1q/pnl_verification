import DataTable, { cellClass, TableSkeleton, totalClass } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import ErrorMessage from "@/components/common/ErrorMessage";
import Pager from "@/components/table/Pager";
import SortHeader, { toggleSort } from "@/components/table/SortHeader";
import { TableCell, TableRow } from "@/components/ui/table";
import { count, formatDay, formatMonth, money, pnlClass } from "@/utils/format";
import { MONTHLY_COLUMNS, PAGE_SIZE } from "./columns";

// Totals for the whole filtered period, from the summary endpoint (unrealized / MTM at period end).
// Trading days are summed from the month rows when all months are on this page.
function TotalsRow({ s, months, rows }) {
  const allShown = rows.length >= months;
  return (
    <>
      <TableCell className={totalClass()}>Total <span className="font-normal text-muted-foreground">· {count(months)} {months === 1 ? "month" : "months"}</span></TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.buy_value)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.sell_value)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{s.opening_value ? money(s.opening_value) : "—"}</TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.net_value)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.realized_pnl) })}>{money(s.realized_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.unrealized_pnl) })} title="As of the last day of the period">{money(s.unrealized_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.broker_mtm) })} title="Realised in the period + unrealised at its end">{money(s.broker_mtm)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.mtm_pnl) })}>{money(s.mtm_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{allShown ? count(rows.reduce((n, r) => n + (r.trading_days || 0), 0)) : "—"}</TableCell>
    </>
  );
}

export default function MonthlyTable({ monthly, summary, sort, setSort, page, setPage }) {
  const header = MONTHLY_COLUMNS.map((c) => <SortHeader key={c.key} column={c} sort={sort} onSort={toggleSort(setSort, setPage)} />);
  const rows = monthly.data?.rows;
  return (
    <>
      <ErrorMessage>{monthly.error}</ErrorMessage>
      {rows?.length ? (
        <DataTable header={header} loading={monthly.loading}
          totals={summary ? <TotalsRow s={summary} months={monthly.data.total} rows={rows} /> : null}
          footer={<Pager page={page} total={monthly.data.total} pageSize={PAGE_SIZE} loading={monthly.loading} onPage={setPage} label="months" />}>
          {rows.map((row) => (
            <TableRow key={row.month}>
              <TableCell className={cellClass()}>
                <div className="font-semibold">{formatMonth(row.month)}</div>
                <div className="text-[11px] text-muted-foreground">{formatDay(row.first_date)} – {formatDay(row.last_date)}</div>
              </TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.buy_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.sell_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{row.opening_value ? money(row.opening_value) : "—"}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.net_value)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.realized_pnl) })}>{money(row.realized_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.unrealized_pnl) })}>{money(row.unrealized_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.broker_mtm) })}>{money(row.broker_mtm)}</TableCell>
              <TableCell className={cellClass({ num: true, tone: pnlClass(row.mtm_pnl) })}>{money(row.mtm_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{count(row.trading_days)}</TableCell>
            </TableRow>
          ))}
        </DataTable>
      ) : monthly.loading ? (
        <TableSkeleton header={header} columns={MONTHLY_COLUMNS.length} />
      ) : (
        <EmptyState title="No P&L for these filters">Change the filters or upload the day's net position.</EmptyState>
      )}
    </>
  );
}
