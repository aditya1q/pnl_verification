import { requestJson, uploadFile } from "@/api/client";
import { useRemote } from "@/hooks/useRemote";
import { count, formatDay } from "@/utils/format";
import ImportControl, { importBar } from "./ImportControl";

// Carry Forward (C/F) status and import: the opening positions of the P&L cycle.
export default function CarryForwardBar({ refreshKey, onImported }) {
  const cf = useRemote((signal) => requestJson("/api/backoffice/carry-forward", { signal }), [refreshKey]);

  async function importFile([file]) {
    const result = await uploadFile("/api/backoffice/carry-forward", file);
    const parts = Object.entries(result.by_exchange).map(([ex, n]) => `${ex} ${count(n)}`).join(" · ");
    onImported();
    return { message: `C/F imported: ${count(result.open_positions)} open positions (${parts}) as of ${formatDay(result.as_of)}. Report totals verified.` };
  }

  const rows = cf.data || [];
  const asOf = rows.reduce((latest, row) => (!latest || row.as_of > latest ? row.as_of : latest), "");
  return (
    <div className={importBar}>
      <span>
        {cf.error ? `Carry Forward unavailable: ${cf.error}`
          : !cf.data ? "Loading Carry Forward…"
          : rows.length
            ? <>Carry Forward as of <strong>{formatDay(asOf)}</strong> (Close Rate) · {rows.map((r) => `${r.exchange} ${count(r.positions)}`).join(" · ")} open positions{rows[0].client ? ` · ${rows[0].client}` : ""} · P&L starts from the next day's net position</>
            : "No Carry Forward imported: positions start flat on the first uploaded day."}
      </span>
      <ImportControl label={rows.length ? "Replace C/F file" : "Import C/F file"} accept=".txt,.csv,.prn"
        title="Broker 'Clientwise Net Position' report (.txt). Replaces the current C/F." onFiles={importFile} />
    </div>
  );
}
