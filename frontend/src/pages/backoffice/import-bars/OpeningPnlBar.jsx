import { requestJson, uploadFile } from "@/api/client";
import { useRemote } from "@/hooks/useRemote";
import { count, formatDay, money, pnlClass, lossText } from "@/utils/format";
import ImportControl, { importBar } from "./ImportControl";

// Broker P&L report as on the C/F date: realised / unrealised so far and the original cost of open positions.
export default function OpeningPnlBar({ refreshKey, onImported }) {
  const status = useRemote((signal) => requestJson("/api/backoffice/opening-pnl", { signal }), [refreshKey]);

  async function importFile([file]) {
    const result = await uploadFile("/api/backoffice/opening-pnl", file);
    onImported();
    return { message: `P&L as on ${formatDay(result.as_of)} imported: ${count(result.contracts)} contracts, ${count(result.open_positions)} open positions match the C/F.` };
  }

  const data = status.data;
  const loaded = data && data.as_of;
  return (
    <div className={importBar}>
      <span>
        {status.error ? `C/F P&L report unavailable: ${status.error}`
          : !data ? "Loading C/F P&L report…"
          : loaded
            ? <>Broker P&L as on <strong>{formatDay(data.as_of)}</strong>: realized <strong className={pnlClass(data.realised_pnl)}>{money(data.realised_pnl)}</strong> · unrealized <strong className={pnlClass(data.unrealised_pnl)}>{money(data.unrealised_pnl)}</strong> · MTM <strong className={pnlClass(data.mtm)}>{money(data.mtm)}</strong>{data.total_charges ? ` · charges ${money(data.total_charges)}` : ""} · C/F carried at the broker's original cost</>
            : <span className={lossText}>No broker P&L report for the C/F date: C/F positions are carried at the C/F Close Rate, and P&L before the C/F is not included.</span>}
      </span>
      <ImportControl label={loaded ? "Replace C/F P&L file" : "Import C/F P&L file"} accept=".csv"
        title="Broker P&L report as on the C/F date (e.g. MOP117_30-10-2026.csv): realised / unrealised P&L and original cost of open positions."
        onFiles={importFile} />
    </div>
  );
}
