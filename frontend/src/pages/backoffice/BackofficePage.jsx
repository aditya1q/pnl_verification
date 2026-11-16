import { useCallback, useEffect, useState } from "react";
import { CalendarDays, CalendarRange, Layers } from "lucide-react";
import { requestJson } from "@/api/client";
import ErrorMessage from "@/components/common/ErrorMessage";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { readHashParams, VIEWS, writeHashParams } from "@/hooks/useHashView";
import { useRemote } from "@/hooks/useRemote";
import { formatDay } from "@/utils/format";
import { PAGE_SIZE } from "./columns";
import DailyTable from "./DailyTable";
import FilterBar from "./FilterBar";
import { applyFilter, EMPTY_FILTERS, filterParams, filtersFromUrl, filtersToUrl } from "./filters";
import MonthlyTable from "./MonthlyTable";
import PositionsTable from "./PositionsTable";
import SummaryCards from "./SummaryCards";

const TABS = [
  { value: "daily", label: "Day-wise P&L", icon: CalendarDays },
  { value: "monthly", label: "Month-wise P&L", icon: CalendarRange },
  { value: "positions", label: "Open positions", icon: Layers },
];

function tabHint(tab, positionsAsOf) {
  if (tab === "daily") return "From each day's net position. C/F and carried positions square off first, then average price. Day P&L = realized + change in unrealized.";
  if (tab === "monthly") return "Month P&L = realized in the month + change in unrealized. The cycle starts from the C/F at Close Rate.";
  return `Open quantity marked to LTP as of ${positionsAsOf ? formatDay(positionsAsOf) : "the latest trading day"}.`;
}

// Paged, sorted report rows from `path`, loaded only while `active`.
function useReport(path, active, filters, sort, page, refreshKey) {
  return useRemote(active ? (signal) => {
    const params = filterParams(filters);
    params.set("sort", sort.key); params.set("order", sort.dir);
    params.set("limit", String(PAGE_SIZE)); params.set("skip", String(page * PAGE_SIZE));
    return requestJson(`${path}?${params}`, { signal });
  } : null, [active, filterParams(filters).toString(), sort.key, sort.dir, page, refreshKey]);
}

export default function BackofficePage() {
  const [filters, setFilters] = useState(() => filtersFromUrl(readHashParams()));
  const [refreshKey, setRefreshKey] = useState(0);
  const [mainTab, setMainTab] = useState("daily");
  const [dailySort, setDailySort] = useState({ key: "date", dir: "desc" });
  const [dailyPage, setDailyPage] = useState(0);
  const [monthSort, setMonthSort] = useState({ key: "month", dir: "desc" });
  const [monthPage, setMonthPage] = useState(0);

  const filterKey = filterParams(filters).toString();

  // Keep the URL in step with the filters (exchange, dates, symbol, instrument).
  useEffect(() => {
    writeHashParams(VIEWS.BACKOFFICE, filtersToUrl(filters));
  }, [filters]);
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  const options = useRemote(
    (signal) => requestJson(`/api/backoffice/options?${new URLSearchParams(filters.exchange ? { exchange: filters.exchange } : {})}`, { signal }),
    [filters.exchange, refreshKey],
  );
  const summary = useRemote(
    (signal) => requestJson(`/api/backoffice/summary?${filterKey}`, { signal }),
    [filterKey, refreshKey],
  );
  const daily = useReport("/api/backoffice/daily", mainTab === "daily", filters, dailySort, dailyPage, refreshKey);
  const monthly = useReport("/api/backoffice/monthly", mainTab === "monthly", filters, monthSort, monthPage, refreshKey);

  const updateFilter = useCallback((name, value) => {
    setFilters((prev) => applyFilter(prev, name, value));
    setDailyPage(0);
    setMonthPage(0);
  }, []);
  const resetFilters = () => { setFilters(EMPTY_FILTERS); setDailyPage(0); setMonthPage(0); };

  const positionsAsOf = filters.date || filters.to || "";

  return (
    <section className="flex flex-col gap-3 sm:min-h-0 sm:flex-1 sm:overflow-hidden" aria-label="Backoffice P&L">
      <FilterBar filters={filters} options={options.data || { symbols: [], instruments: [] }}
        onChange={updateFilter} onReset={resetFilters} />

      <ErrorMessage>{summary.error}</ErrorMessage>
      <SummaryCards summary={summary.data} loading={summary.loading} />

      <Tabs value={mainTab} onValueChange={setMainTab} className="flex min-h-[320px] flex-col gap-3 sm:min-h-0 sm:flex-1 sm:overflow-hidden">
        <div className="flex shrink-0 flex-wrap items-center gap-3">
          <TabsList>
            {TABS.map(({ value, label, icon: Icon }) => (
              <TabsTrigger key={value} value={value} className="px-3 text-xs"><Icon /> {label}</TabsTrigger>
            ))}
          </TabsList>
          <span className="text-xs text-muted-foreground">{tabHint(mainTab, positionsAsOf)}</span>
        </div>
        {mainTab === "positions" ? (
          <PositionsTable key={`${filterKey}|${positionsAsOf}`} filters={filters} asOf={positionsAsOf} refreshKey={refreshKey} onChanged={refresh} />
        ) : mainTab === "monthly" ? (
          <MonthlyTable monthly={monthly} summary={summary.data} sort={monthSort} setSort={setMonthSort} page={monthPage} setPage={setMonthPage} />
        ) : (
          <DailyTable daily={daily} summary={summary.data} sort={dailySort} setSort={setDailySort} page={dailyPage} setPage={setDailyPage} />
        )}
      </Tabs>
    </section>
  );
}
