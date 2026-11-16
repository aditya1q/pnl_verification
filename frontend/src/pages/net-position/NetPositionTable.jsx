import DataTable, { cellClass, TableSkeleton } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import ErrorMessage from "@/components/common/ErrorMessage";
import ToneBadge from "@/components/common/ToneBadge";
import Pager from "@/components/table/Pager";
import SortHeader from "@/components/table/SortHeader";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatDate, money, pnlClass, quantity } from "@/utils/format";
import { COLUMNS, PAGE_SIZE } from "./columns";

function OptionBadge({ type }) {
  if (type === "FX") return <ToneBadge>FUT</ToneBadge>;
  return <ToneBadge tone={type === "CE" ? "call" : "put"}>{type}</ToneBadge>;
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("truncate text-sm font-semibold tabular-nums", tone)}>{value}</div>
      {sub && <div className="truncate text-[11px] text-muted-foreground tabular-nums">{sub}</div>}
    </div>
  );
}

export default function NetPositionTable({ exchange, viewDate, data, loading, error, searching, sort, onSort, page, onPage }) {
  const total = data?.total || 0;
  const totals = data?.totals;
  const header = COLUMNS.map((column) => <SortHeader key={column.label} column={column} sort={sort} onSort={onSort} />);
  return (
    <section className="flex min-h-[320px] flex-col gap-3 sm:min-h-0 sm:flex-1">
      <ErrorMessage>{error}</ErrorMessage>
      {totals && total > 0 && (
        <div className={cn("grid shrink-0 grid-cols-2 divide-x divide-y rounded-xl border bg-card shadow-card transition-opacity duration-200 sm:grid-cols-5 sm:divide-y-0", loading && "opacity-55")}>
          <Stat label={`${exchange} · ${formatDate(viewDate)}`} value={`${quantity(total)} contracts`} sub={searching ? "filtered by search" : undefined} />
          <Stat label="Buy value" value={money(totals.buy_value)} sub={`Qty ${quantity(totals.buy_qty)}`} />
          <Stat label="Sale value" value={money(totals.sell_value)} sub={`Qty ${quantity(totals.sell_qty)}`} />
          <Stat label="Net qty" value={quantity(totals.net_qty)} />
          <Stat label="Net value" value={money(totals.net_value)} tone={pnlClass(totals.net_value)} sub="Sale − Buy" />
        </div>
      )}
      {data?.rows?.length > 0 ? (
        <DataTable header={header} loading={loading}
          footer={<Pager page={page} total={total} pageSize={PAGE_SIZE} loading={loading} onPage={onPage} label="contracts" />}>
          {data.rows.map((row) => (
            <TableRow key={`${row.source_line}-${row.symbol}-${row.strike}-${row.option_type}`}>
              <TableCell className={cellClass({ muted: true })}>{row.instrument_name}</TableCell>
              <TableCell className={cellClass()}><span className="font-semibold">{row.underlying}</span> <span className="text-muted-foreground">{row.symbol}</span></TableCell>
              <TableCell className={cellClass()}>{row.expiry}</TableCell>
              <TableCell className={cellClass({ num: true })}>{row.option_type === "FX" ? "—" : quantity(row.strike)}</TableCell>
              <TableCell className={cellClass()}><OptionBadge type={row.option_type} /></TableCell>
              <TableCell className={cellClass({ num: true })}>{quantity(row.buy_qty)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.buy_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{quantity(row.sell_qty)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.sell_value)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.net_qty) })}>{quantity(row.net_qty)}</TableCell>
              <TableCell className={cellClass({ num: true, tone: pnlClass(row.net_value) })}>{money(row.net_value)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{money(row.avg_rate)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true })}>{money(row.close_rate)}</TableCell>
              <TableCell className={cellClass({ num: true, tone: pnlClass(row.mtm) })}>{money(row.mtm)}</TableCell>
              <TableCell className={cellClass({ muted: true })}>{row.report_exchange || "—"}</TableCell>
            </TableRow>
          ))}
        </DataTable>
      ) : loading ? (
        <TableSkeleton header={header} columns={COLUMNS.length} />
      ) : (
        <EmptyState title={searching ? "No contracts match the search" : `No ${exchange} net position for ${formatDate(viewDate) || "this day"}`}>
          Choose a highlighted date or upload the day's net position report.
        </EmptyState>
      )}
    </section>
  );
}
