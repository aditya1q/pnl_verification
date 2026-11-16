import { useState } from "react";
import { CircleCheck, X } from "lucide-react";
import { requestJson } from "@/api/client";
import DataTable, { cellClass, TableSkeleton } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import ErrorMessage from "@/components/common/ErrorMessage";
import ToneBadge from "@/components/common/ToneBadge";
import Pager from "@/components/table/Pager";
import SortHeader, { toggleSort } from "@/components/table/SortHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { useRemote } from "@/hooks/useRemote";
import { cn } from "@/lib/utils";
import { contractLabel, positionKey } from "@/utils/contracts";
import { count, formatDay, money, pnlClass, price } from "@/utils/format";
import { PAGE_SIZE, POSITION_COLUMNS } from "./columns";
import { filterParams } from "./filters";
import LtpCell from "./LtpCell";

function PositionsSummary({ summary, asOf }) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-muted-foreground">
      <span>As of <strong className="text-foreground">{formatDay(asOf)}</strong> (end of day)</span>
      <span>{count(summary.open_positions)} open positions</span>
      <span>Long qty <span className="tabular-nums text-foreground">{count(summary.open_long_qty)}</span></span>
      <span>Short qty <span className="tabular-nums text-foreground">{count(summary.open_short_qty)}</span></span>
      <span>Unrealized <strong className={cn("tabular-nums text-foreground", pnlClass(summary.unrealized_pnl))}>{money(summary.unrealized_pnl)}</strong></span>
      {summary.missing_ltp > 0 && <ToneBadge tone="short">{summary.missing_ltp} without LTP (counted as 0)</ToneBadge>}
      {summary.stale_ltp > 0 && (
        <ToneBadge tone="warn" title="These positions are marked to an older price (e.g. the C/F close); set their LTP for this date">
          {summary.stale_ltp} priced before {formatDay(asOf)}
        </ToneBadge>
      )}
    </div>
  );
}

export default function PositionsTable({ filters, asOf, refreshKey, onChanged }) {
  const [sort, setSort] = useState({ key: "unrealized_pnl", dir: "asc" });
  const [page, setPage] = useState(0);
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState("");
  const ltpChanged = (message) => { setNotice(message); setReload((v) => v + 1); onChanged(); };

  const params = filterParams(filters, asOf);
  params.set("sort", sort.key); params.set("order", sort.dir);
  params.set("limit", String(PAGE_SIZE)); params.set("skip", String(page * PAGE_SIZE));
  if (asOf) params.set("as_of", asOf);
  const query = params.toString();
  const positions = useRemote((signal) => requestJson(`/api/backoffice/positions?${query}`, { signal }), [query, refreshKey, reload]);

  const data = positions.data;
  const header = POSITION_COLUMNS.map((c) => <SortHeader key={c.label} column={c} sort={sort} onSort={toggleSort(setSort, setPage)} />);
  return (
    <>
      <ErrorMessage>{positions.error}</ErrorMessage>
      {notice && (
        <Alert className="border-emerald-200 bg-emerald-50 py-2 text-emerald-800">
          <CircleCheck />
          <AlertDescription className="flex items-center justify-between gap-3 text-emerald-800">
            <span>{notice}</span>
            <Button variant="ghost" size="icon" className="size-6 text-emerald-800 hover:bg-emerald-100" onClick={() => setNotice("")} aria-label="Dismiss"><X /></Button>
          </AlertDescription>
        </Alert>
      )}
      {data?.summary && <PositionsSummary summary={data.summary} asOf={data.as_of} />}
      {data?.rows?.length ? (
        <DataTable header={header} loading={positions.loading}
          footer={<Pager page={page} total={data.total} pageSize={PAGE_SIZE} loading={positions.loading} onPage={setPage} label="open positions" />}>
          {data.rows.map((row) => (
            <TableRow key={positionKey(row)}>
              <TableCell className={cellClass()}>
                <span className="font-semibold">{contractLabel(row)}</span> <span className="text-muted-foreground">{row.expiry}</span>
                {row.carried_forward && <ToneBadge tone="cf" className="ml-1.5" title="Includes Carry Forward opening position">C/F</ToneBadge>}
              </TableCell>
              <TableCell className={cellClass()}>
                <ToneBadge tone={row.side === "LONG" ? "long" : "short"}>{row.side === "LONG" ? "Long" : "Short"}</ToneBadge>
              </TableCell>
              <TableCell className={cellClass({ num: true })}>{count(row.open_qty)}</TableCell>
              <TableCell className={cellClass({ num: true })}>{price(row.avg_price)}</TableCell>
              <TableCell className={cellClass({ num: true, strong: true })}>{price(row.ltp)}</TableCell>
              <TableCell className={cellClass()}><LtpCell row={row} asOf={data.as_of} onSaved={ltpChanged} /></TableCell>
              <TableCell className={cellClass({ num: true, strong: true, tone: pnlClass(row.unrealized_pnl) })}>{money(row.unrealized_pnl)}</TableCell>
            </TableRow>
          ))}
        </DataTable>
      ) : positions.loading ? (
        <TableSkeleton header={header} columns={POSITION_COLUMNS.length} />
      ) : (
        <EmptyState title="No open positions">All quantity is squared off for these filters, so unrealized P&L is 0.</EmptyState>
      )}
    </>
  );
}
