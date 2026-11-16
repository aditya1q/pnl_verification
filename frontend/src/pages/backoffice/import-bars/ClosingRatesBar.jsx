import { requestJson, uploadFile } from "@/api/client";
import { useRemote } from "@/hooks/useRemote";
import { count, formatDay, lossText } from "@/utils/format";
import ImportControl, { importBar } from "./ImportControl";

// Days with a net position report loaded, and import of one more day.
export default function ClosingRatesBar({ refreshKey, onImported }) {
  const rates = useRemote((signal) => requestJson("/api/backoffice/closing-rates", { signal }), [refreshKey]);

  async function importFile([file]) {
    const result = await uploadFile("/api/backoffice/closing-rates", file);
    const parts = Object.entries(result.by_exchange).map(([ex, n]) => `${ex} ${count(n)}`).join(" · ");
    const gaps = Object.entries(result.missing_days || {}).map(([ex, days]) => `${ex} ${days.map(formatDay).join(", ")}`);
    onImported();
    return {
      message: `Net position for ${formatDay(result.date)} imported: ${count(result.contracts)} contracts (${parts}), totals verified.`,
      error: gaps.length ? `Note: no data for ${gaps.join(" · ")}: import those days unless they were holidays.` : "",
    };
  }

  const rows = rates.data || [];
  const days = [...new Set(rows.filter((r) => r.net_position).map((r) => r.date))].sort().reverse();
  const listed = days.slice(0, 5).map(formatDay).join(", ") + (days.length > 5 ? ` +${days.length - 5} more` : "");
  return (
    <div className={importBar}>
      <span>
        {rates.error ? `Net positions unavailable: ${rates.error}`
          : !rates.data ? "Loading net positions…"
          : days.length
            ? <>Daily net position loaded for <strong>{listed}</strong> · P&L uses each day's buy/sell totals and Close Rates</>
            : <span className={lossText}>No daily net position imported yet. Upload each day's net position report.</span>}
      </span>
      <ImportControl label="Import day's net position" accept=".xls,.csv,.txt,.prn"
        title="Broker daily 'Net Position' report for one day (.csv, .xls or .txt). Re-importing a day replaces it." onFiles={importFile} />
    </div>
  );
}
