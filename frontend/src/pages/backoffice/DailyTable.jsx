import DataTable, { cellClass, TableSkeleton, totalClass } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import ErrorMessage from "@/components/common/ErrorMessage";
import Pager from "@/components/table/Pager";
import SortHeader, { toggleSort } from "@/components/table/SortHeader";
import { TableCell, TableRow } from "@/components/ui/table";
import { count, formatDay, money, pnlClass } from "@/utils/format";
import { DAILY_COLUMNS, PAGE_SIZE } from "./columns";

// Totals for the whole filtered period (all pages), from the summary endpoint.
// Unrealized and MTM are end-of-period values, not sums of the days.
function TotalsRow({ s, days }) {
  return (
    <>
      <TableCell className={totalClass()}>Total <span className="font-normal text-muted-foreground">· {count(days)} days</span></TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.buy_value)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.sell_value)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{money(s.net_value)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.realized_pnl) })}>{money(s.realized_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.unrealized_pnl) })} title="As of the last day of the period">{money(s.unrealized_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.broker_mtm) })} title="Realised in the period + unrealised at its end">{money(s.broker_mtm)}</TableCell>
      <TableCell className={totalClass({ num: true, tone: pnlClass(s.mtm_pnl) })}>{money(s.mtm_pnl)}</TableCell>
      <TableCell className={totalClass({ num: true })}>{count(s.matched_trades)}</TableCell>
    </>
  );
}

export default function DailyTable({ daily, summary, sort, setSort, page, setPage }) {
  const header = DAILY_COLUMNS.map((c) => <SortHeader key={c.key} column={c} sort={sort} onSort={toggleSort(setSort, setPage)} />);
  const rows = daily.data?.rows;
  return (
    <>
      <ErrorMessage>{daily.error}</ErrorMessage>
      {rows?.length ? (
        <DataTable header={header} loading={daily.loading}
          totals={summary ? <TotalsRow s={summary} days={daily.data.total} /> : null}
          footer={<Pager page={page} total={daily.data.total} pageSize={PAGE_SIZE} loading={daily.loading} onPage={setPage} label="trading days" />}>
          {rows.map((row) => (
            <TableRow key={row.date}>
              <TableCell className={cellClass({ strong: true })}>{formatDay(row.date)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.buy_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.sell_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.net_value)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.realized_pnl) })}>{money(row.realized_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.unrealized_pnl) })}>{money(row.unrealized_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.broker_mtm) })}>{money(row.broker_mtm)}</TableCell>
              <TableCell className={cellClass({ num: true, tone: pnlClass(row.mtm_pnl) })}>{money(row.mtm_pnl)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{count(row.matched_trades)}</TableCell>
            </TableRow>
          ))}
        </DataTable>
      ) : daily.loading ? (
        <TableSkeleton header={header} columns={DAILY_COLUMNS.length} />
      ) : (
        <EmptyState title="No P&L for these filters">Change the filters or upload the day's net position.</EmptyState>
      )}
    </>
  );
}
