import { uploadFile } from "@/api/client";
import { formatDay } from "@/utils/format";
import ImportControl, { importBar } from "./ImportControl";

// "MOP117_02-11-2026.XLS" -> "20261102", so files sort oldest day first.
function fileDay(file) {
  return (file.name.match(/(\d{2})-(\d{2})-(\d{4})/) || []).slice(1).reverse().join("");
}

// Checks days against the broker's daily "Realised & Unrealised" reports.
export default function BrokerPnlBar({ onImported }) {
  async function checkFiles(files) {
    const done = [];
    try {
      for (const file of [...files].sort((x, y) => fileDay(x).localeCompare(fileDay(y)))) {
        const r = await uploadFile("/api/backoffice/broker-pnl", file);
        done.push(`${formatDay(r.date)}: ${r.still_different.length ? `${r.still_different.length} contract(s) still differ` : "matches broker"}${r.calibrated_contracts ? ` (${r.calibrated_contracts} C/F lot(s) corrected)` : ""}`);
      }
    } catch (err) {
      err.partialMessage = done.join(" · ");
      throw err;
    }
    onImported();
    return { message: done.join(" · ") };
  }

  return (
    <div className={importBar}>
      <span>Broker P&L check: upload the broker's daily "Realised & Unrealised" reports (MOP117_dd-mm-yyyy) to verify a day. Pre-C/F lots closed that day are corrected to the broker's cost.</span>
      <ImportControl label="Check with broker P&L" busyLabel="Checking…" accept=".xls,.csv" multiple
        title="One or more broker P&L reports (.XLS / .csv); they are applied oldest day first." onFiles={checkFiles} />
    </div>
  );
}
