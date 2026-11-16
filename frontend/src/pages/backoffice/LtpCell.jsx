import { useState } from "react";
import { Check, Pencil, RotateCcw, X } from "lucide-react";
import { requestJson } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import ToneBadge from "@/components/common/ToneBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { contractLabel } from "@/utils/contracts";
import { formatDay, lossText, price } from "@/utils/format";

function LtpSource({ row, stale }) {
  const when = stale ? ` ${formatDay(row.ltp_date)}` : "";
  switch (row.ltp_source) {
    case "MANUAL":
      return <ToneBadge tone="warn">Manual{when}</ToneBadge>;
    case "BROKER_CLOSE":
      return <ToneBadge tone={stale ? "warn" : "close"} title="Official Close Rate from the broker's net position report">Close rate{when}</ToneBadge>;
    case "BHAVCOPY":
      return <ToneBadge tone={stale ? "warn" : "close"} title="Exchange closing price from the F&O bhavcopy (not traded that day)">Bhavcopy{when}</ToneBadge>;
    case "CF_CLOSE":
      return (
        <ToneBadge tone={stale ? "short" : "neutral"} title={stale ? "Not in this day's net position (did not trade): set the LTP for this date" : undefined}>
          C/F close {formatDay(row.ltp_date)}
        </ToneBadge>
      );
    default:
      return <ToneBadge tone="short">No price</ToneBadge>;
  }
}

// LTP source badge with inline "Set LTP" / "Reset" for a manual price on the as-of date.
export default function LtpCell({ row, asOf, onSaved }) {
  const { canWrite } = useAuth();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const send = (method, extra = {}) => requestJson("/api/backoffice/ltp", {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      exchange: row.exchange, symbol: row.symbol, expiry: row.expiry, strike: row.strike,
      option_type: row.option_type, date: asOf, ...extra,
    }),
  });

  async function save(event) {
    event.preventDefault();
    const ltp = Number(value);
    if (value === "" || !Number.isFinite(ltp) || ltp < 0) { setError("Enter a valid price."); return; }
    setSaving(true); setError("");
    try {
      await send("PUT", { ltp });
      setEditing(false);
      onSaved(`LTP ${price(ltp)} saved for ${row.exchange} ${contractLabel(row)} (${row.expiry}) on ${formatDay(asOf)}.`);
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }

  async function clearManual() {
    setSaving(true); setError("");
    try {
      await send("DELETE");
      onSaved(`Manual LTP removed for ${row.exchange} ${contractLabel(row)} (${row.expiry}) on ${formatDay(asOf)}; using the Close Rate again.`);
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }

  if (editing) {
    return (
      <form className="flex items-center gap-1" onSubmit={save}>
        <Input type="number" step="0.05" min="0" value={value} autoFocus aria-label={`LTP for ${contractLabel(row)} on ${asOf}`}
          className="h-7 w-24 text-right text-xs"
          onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }} />
        <Button type="submit" size="icon" variant="ghost" className="size-7 text-profit" disabled={saving} aria-label="Save LTP"><Check /></Button>
        <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => setEditing(false)} disabled={saving} aria-label="Cancel"><X /></Button>
        {error && <span className={lossText}>{error}</span>}
      </form>
    );
  }
  const stale = Boolean(row.ltp_date && row.ltp_date !== asOf);
  return (
    <div className="flex items-center gap-1.5">
      <LtpSource row={row} stale={stale} />
      {canWrite && <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-xs text-primary" disabled={saving}
        onClick={() => { setValue(row.ltp ?? ""); setError(""); setEditing(true); }}><Pencil className="size-3" /> Set LTP</Button>}
      {canWrite && row.ltp_source === "MANUAL" && row.ltp_date === asOf && (
        <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-xs text-muted-foreground" disabled={saving} onClick={clearManual}>
          <RotateCcw className="size-3" /> Reset</Button>
      )}
      {error && <span className={lossText}>{error}</span>}
    </div>
  );
}
