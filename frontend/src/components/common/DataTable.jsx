import Skeleton from "@/components/common/Skeleton";
import { Table, TableBody, TableCell, TableFooter, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Row colours are opaque so the pinned first column shows the same colour as its row.
const ROWS = cn(
  "[&_tbody_tr]:bg-card [&_tbody_tr:nth-child(even)]:bg-zebra [&_tbody_tr:hover]:bg-row-hover",
  "[&_tbody_tr]:border-b-border/60",
);
// First column stays visible when the table scrolls sideways.
const PIN_FIRST = cn(
  "[&_tr>*:first-child]:sticky [&_tr>*:first-child]:left-0",
  "[&_tbody_tr>*:first-child]:z-[1] [&_tbody_tr>*:first-child]:bg-inherit [&_tbody_tr>*:first-child]:shadow-[inset_-1px_0_0_var(--border)]",
  "[&_thead_tr>*:first-child]:z-20 [&_thead_tr>*:first-child]:shadow-[inset_-1px_0_0_var(--border),inset_0_-1px_0_var(--border)]",
  "[&_tfoot_tr>*:first-child]:z-20 [&_tfoot_tr>*:first-child]:shadow-[inset_-1px_0_0_var(--border),inset_0_1px_0_var(--border)]",
);

// Card-framed table that fills the remaining height and scrolls inside, with a sticky header row,
// a pinned first column and an optional totals row pinned to the bottom (`totals` = footer cells).
// `header` is the header cells; `footer` (e.g. a Pager) sits below the scroll area.
// While `loading`, the current rows stay visible but dimmed, so switching dates doesn't flicker.
export default function DataTable({ header, children, totals, footer, loading = false, className }) {
  return (
    <div aria-busy={loading || undefined}
      className={cn("flex min-h-[260px] flex-col overflow-hidden rounded-xl border bg-card shadow-card sm:min-h-0 sm:flex-1", className)}>
      <Table containerClassName={cn("max-h-[60vh] flex-1 overflow-auto overscroll-contain transition-opacity duration-200 sm:max-h-none", loading && "opacity-55")}
        className={cn("text-xs", ROWS, PIN_FIRST)}>
        <TableHeader className="sticky top-0 z-10 bg-muted [&_tr]:border-b-0">
          <TableRow className="hover:bg-transparent">{header}</TableRow>
        </TableHeader>
        <TableBody>{children}</TableBody>
        {totals && (
          <TableFooter className="sticky bottom-0 z-10 border-t-0 bg-muted">
            <TableRow className="hover:bg-transparent">{totals}</TableRow>
          </TableFooter>
        )}
      </Table>
      {footer}
    </div>
  );
}

// Placeholder table for the first load: the real header with pulsing rows.
export function TableSkeleton({ header, rows = 8, columns }) {
  const widths = ["w-16", "w-24", "w-20", "w-14", "w-28", "w-12"];
  return (
    <DataTable header={header}>
      {Array.from({ length: rows }, (_, r) => (
        <TableRow key={r} className="hover:bg-transparent">
          {Array.from({ length: columns }, (_, c) => (
            <TableCell key={c} className="px-3 py-2.5">
              <Skeleton className={cn("h-3", widths[(r + c) % widths.length], c > 0 && "ml-auto")} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </DataTable>
  );
}

// Class for a header cell: muted, small caps (the whole header row is sticky). `num` right-aligns numbers.
export function headClass(num = false) {
  return cn(
    "h-9 bg-muted px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground shadow-[inset_0_-1px_0_var(--border)]",
    num && "text-right",
  );
}

// Class for a body cell. `num` right-aligns with tabular figures; `tone` is a pnlClass() result.
export function cellClass({ num = false, strong = false, muted = false, tone = "" } = {}) {
  return cn(
    "px-3 py-2",
    num && "text-right tabular-nums",
    strong && "font-semibold",
    muted && "text-muted-foreground",
    tone,
  );
}

// Class for a totals-row cell (the whole totals row is pinned to the bottom of the scroll area).
export function totalClass({ num = false, tone = "", muted = false } = {}) {
  return cn(
    "bg-muted px-3 py-2.5 font-semibold shadow-[inset_0_1px_0_var(--border)]",
    num && "text-right tabular-nums",
    muted && "font-normal text-muted-foreground",
    tone,
  );
}
