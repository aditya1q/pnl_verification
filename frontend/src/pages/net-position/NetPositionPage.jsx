import { useEffect, useMemo, useState } from "react";
import { Search, Upload } from "lucide-react";
import { requestJson } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import SegmentedControl from "@/components/common/SegmentedControl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { readHashParams, VIEWS, writeHashParams } from "@/hooks/useHashView";
import { cn } from "@/lib/utils";
import { dateString, MONTH_NAMES, today } from "@/utils/dates";
import { PAGE_SIZE } from "./columns";
import NetPositionTable from "./NetPositionTable";
import UploadModal from "./UploadModal";
import UploadResultModal from "./UploadResultModal";

const EXCHANGES = [{ value: "NSE", label: "NSE" }, { value: "BSE", label: "BSE" }];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Initial exchange / date from the URL (#netposition?exchange=BSE&date=2026-11-12); invalid values are ignored.
function initialParams() {
  const params = readHashParams();
  const exchange = String(params.exchange || "").toUpperCase();
  return {
    exchange: EXCHANGES.some((e) => e.value === exchange) ? exchange : "NSE",
    date: DATE_RE.test(params.date || "") ? params.date : "",
  };
}

function DateStrip({ year, month, viewDate, loadedDays, onPick }) {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  return (
    <div className="grid grid-cols-8 gap-1.5 sm:grid-cols-16" role="group" aria-label="Choose date">
      {Array.from({ length: daysInMonth }, (_, index) => index + 1).map((day) => {
        const value = dateString(year, month, day);
        const selected = viewDate === value;
        const hasData = loadedDays.has(value);
        return (
          <button key={value} type="button" onClick={() => onPick(value)} aria-pressed={selected}
            title={hasData ? "Net position imported" : "No net position for this day"}
            className={cn(
              "relative h-8 cursor-pointer rounded-md border text-xs tabular-nums transition-colors",
              selected ? "border-primary bg-primary font-semibold text-primary-foreground shadow-sm"
                : hasData ? "border-emerald-200 bg-emerald-50 font-semibold text-emerald-800 hover:bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300 dark:hover:bg-emerald-950"
                  : "bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}>
            {day} {MONTH_NAMES[month].slice(0, 3)}
            {hasData && !selected && <span className="absolute top-1 right-1 size-1.5 rounded-full bg-emerald-500" aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}

export default function NetPositionPage() {
  const { canWrite } = useAuth();
  const [initial] = useState(initialParams);
  const [exchange, setExchange] = useState(initial.exchange);
  const [viewDate, setViewDate] = useState(initial.date);
  const [days, setDays] = useState([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [dataError, setDataError] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState({ key: "line", dir: "asc" });
  const [searchText, setSearchText] = useState("");
  const [daysKey, setDaysKey] = useState(0);

  const shownDate = viewDate || today();
  const selected = new Date(`${shownDate}T00:00:00`);
  const selectedYear = selected.getFullYear();
  const selectedMonth = selected.getMonth();
  const years = Array.from({ length: 9 }, (_, i) => selectedYear - 5 + i);
  const loadedDays = useMemo(() => new Set(days.filter((d) => d.exchange === exchange).map((d) => d.date)), [days, exchange]);

  // Keep the URL in step with the selected exchange and date.
  useEffect(() => {
    writeHashParams(VIEWS.NET_POSITION, { exchange, date: viewDate });
  }, [exchange, viewDate]);

  // Imported days; open on the newest one (unless the URL named a date).
  useEffect(() => {
    requestJson("/api/net-positions/days")
      .then((rows) => {
        setDays(rows || []);
        setViewDate((current) => current || (rows && rows.length ? rows[0].date : today()));
      })
      .catch((err) => setDataError(err.message));
  }, [daysKey]);

  useEffect(() => {
    if (!viewDate) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true); setDataError("");
      try {
        const params = new URLSearchParams({
          exchange, trade_date: viewDate, sort: sort.key, order: sort.dir,
          limit: String(PAGE_SIZE), skip: String(page * PAGE_SIZE),
        });
        if (searchText.trim()) params.set("search", searchText.trim());
        setData(await requestJson(`/api/net-positions?${params}`, { signal: controller.signal }));
      } catch (err) {
        if (err.name !== "AbortError") { setData(null); setDataError(err.message); }
      } finally { setLoading(false); }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [exchange, viewDate, page, sort.key, sort.dir, searchText, daysKey]);

  function changeViewDate(value) { setViewDate(value); setPage(0); }
  function changeMonth(monthIndex) {
    const day = Math.min(selected.getDate(), new Date(selectedYear, Number(monthIndex) + 1, 0).getDate());
    changeViewDate(dateString(selectedYear, Number(monthIndex), day));
  }
  function changeYear(year) {
    const day = Math.min(selected.getDate(), new Date(Number(year), selectedMonth + 1, 0).getDate());
    changeViewDate(dateString(Number(year), selectedMonth, day));
  }
  function changeSort(key) {
    setSort((prev) => ({ key, dir: prev.key === key && prev.dir === "asc" ? "desc" : "asc" }));
    setPage(0);
  }
  function handleImported(result) {
    setUploadResult(result); setUploadOpen(false);
    setViewDate(result.date); setPage(0); setDaysKey((v) => v + 1);
  }

  return (
    <>
      <section className="flex shrink-0 flex-col gap-3 rounded-xl border bg-card p-3 shadow-card" aria-label="Net position controls">
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl label="Exchange" options={EXCHANGES} value={exchange}
            onChange={(value) => { setExchange(value); setPage(0); }} />
          <div className="relative min-w-[180px] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input type="search" aria-label="Search contracts" placeholder="Search symbol, strike, CE/PE…" className="h-8 pl-8 text-sm"
              value={searchText} onChange={(event) => { setSearchText(event.target.value); setPage(0); }} />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Select value={String(selectedMonth)} onValueChange={changeMonth}>
              <SelectTrigger size="sm" className="w-[120px]" aria-label="Month"><SelectValue /></SelectTrigger>
              <SelectContent>{MONTH_NAMES.map((month, index) => <SelectItem key={month} value={String(index)}>{month}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={String(selectedYear)} onValueChange={changeYear}>
              <SelectTrigger size="sm" className="w-[88px]" aria-label="Year"><SelectValue /></SelectTrigger>
              <SelectContent>{years.map((year) => <SelectItem key={year} value={String(year)}>{year}</SelectItem>)}</SelectContent>
            </Select>
            {canWrite && <Button size="sm" onClick={() => setUploadOpen(true)}><Upload /> Upload net position</Button>}
          </div>
        </div>
        <DateStrip year={selectedYear} month={selectedMonth} viewDate={viewDate} loadedDays={loadedDays} onPick={changeViewDate} />
      </section>

      <NetPositionTable exchange={exchange} viewDate={viewDate} data={data} loading={loading} error={dataError}
        searching={Boolean(searchText.trim())} sort={sort} onSort={changeSort} page={page} onPage={setPage} />

      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onImported={handleImported} />
      <UploadResultModal result={uploadResult} onClose={() => setUploadResult(null)} />
    </>
  );
}
