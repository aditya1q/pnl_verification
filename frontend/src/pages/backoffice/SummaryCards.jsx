import { Activity, ArrowDownToLine, ArrowUpFromLine, CircleCheck, Layers, Scale, TrendingUp } from "lucide-react";
import Skeleton from "@/components/common/Skeleton";
import { cn } from "@/lib/utils";
import { count, formatDay, money, pnlClass } from "@/utils/format";

const PLACEHOLDERS = [
  ["Buy Value", ArrowDownToLine], ["Sell Value", ArrowUpFromLine], ["C/F Opening", Layers], ["Net Value", Scale],
  ["Realized P&L", CircleCheck], ["Unrealized P&L", Activity], ["MTM", TrendingUp],
].map(([label, icon]) => ({ label, icon }));

function buildCards(s) {
  return [
    { label: "Buy Value", icon: ArrowDownToLine, value: money(s.buy_value), sub: `Qty ${count(s.buy_qty)}` },
    { label: "Sell Value", icon: ArrowUpFromLine, value: money(s.sell_value), sub: `Qty ${count(s.sell_qty)}` },
    { label: "C/F Opening", icon: Layers, value: s.cf_as_of ? money(s.opening_value) : "—",
      sub: !s.cf_as_of ? "No Carry Forward" : s.opening_included
        ? `As of ${formatDay(s.cf_as_of)} · long ${count(s.opening_long_qty)} · short ${count(s.opening_short_qty)}`
        : `Not in this period (cycle starts ${formatDay(s.cycle_start)})`,
      hint: "Carry Forward positions at Close Rate: long counted as bought value, short as sold value" },
    { label: "Net Value", icon: Scale, value: money(s.net_value), sub: "Sell value − Buy value (net position)",
      hint: "As in the broker's net position report: negative = net buying. Cash-flow figure, not P&L; the C/F opening is shown separately" },
    { label: "Realized P&L", icon: CircleCheck, value: money(s.realized_pnl), tone: pnlClass(s.realized_pnl),
      sub: `${count(s.matched_qty)} qty squared off · ${count(s.matched_trades)} contract-days`,
      hint: s.cost_basis === "BROKER_COST" ? "C/F positions squared off against the broker's original cost" : "C/F positions squared off against the C/F Close Rate" },
    { label: "Unrealized P&L", icon: Activity, value: money(s.unrealized_pnl), tone: pnlClass(s.unrealized_pnl),
      sub: s.as_of ? `${count(s.open_positions)} open · as of ${formatDay(s.as_of)}${s.stale_ltp ? ` · ${count(s.stale_ltp)} on old price` : ""}` : "No open positions",
      hint: "Open quantity marked to LTP at end of the as-of date" },
    { label: "MTM", icon: TrendingUp, value: money(s.broker_mtm), tone: pnlClass(s.broker_mtm),
      sub: `Realised + unrealised · change vs previous close ${money(s.mtm_pnl)}`,
      hint: "As the broker's MTM column: realised in the period + unrealised (at cost) at its end. The change vs previous close removes the unrealised carried in." },
  ];
}

export default function SummaryCards({ summary, loading }) {
  const cards = summary ? buildCards(summary) : PLACEHOLDERS;
  return (
    <div className={cn("grid shrink-0 grid-cols-2 gap-3 transition-opacity duration-200 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7", summary && loading && "opacity-55")}
      aria-busy={loading || undefined}>
      {cards.map(({ label, icon: Icon, value, sub, tone, hint }) => (
        <div key={label} title={hint} className="flex min-w-0 flex-col gap-1 rounded-xl border bg-card p-3 shadow-card transition-colors hover:border-ring/40">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
            <Icon className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />
          </div>
          {value === undefined && loading ? (
            <><Skeleton className="mt-1 h-5 w-24" /><Skeleton className="mt-1 h-3 w-32" /></>
          ) : (
            <>
              <strong className={cn("truncate font-display text-base font-bold tabular-nums", tone)}>{value ?? "—"}</strong>
              {sub && <small className="truncate text-[11px] text-muted-foreground">{sub}</small>}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
