import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { formatDate, lossText, money, quantity } from "@/utils/format";

function Detail({ label, children, warn = false }) {
  return (
    <div className="flex justify-between gap-4 px-3 py-2 text-sm">
      <span className={cn("text-muted-foreground", warn && lossText)}>{label}</span>
      <span className={cn("text-right font-medium", warn && lossText)}>{children}</span>
    </div>
  );
}

function bhavcopyText(bhavcopy) {
  const imported = (bhavcopy.imported || [])
    .map((b) => `${b.exchange} ${quantity(b.closing_rates)} closes${b.settlements ? ` · ${quantity(b.settlements)} expiry settlements` : ""}`)
    .join(" · ");
  const errors = Object.entries(bhavcopy.errors || {}).map(([ex, msg]) => ` · ${ex}: ${msg}`).join("");
  return (imported || "not downloaded") + errors;
}

// Summary shown after a net position report is imported. Hidden while `result` is null.
export default function UploadResultModal({ result, onClose }) {
  const gaps = Object.entries(result?.missing_days || {});
  return (
    <Dialog open={Boolean(result)} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        {result && (
          <>
            <DialogHeader className="items-center text-center">
              <div className="mb-1 grid size-11 place-items-center rounded-full bg-emerald-50 text-emerald-600"><CheckCircle2 className="size-6" /></div>
              <DialogTitle>Net position imported</DialogTitle>
              <DialogDescription>Totals were checked against the report.</DialogDescription>
            </DialogHeader>
            <div className="divide-y rounded-lg border">
              <Detail label="Date">{formatDate(result.date)}</Detail>
              {result.client && <Detail label="Client">{result.client}</Detail>}
              <Detail label="Contracts">{quantity(result.contracts)} ({Object.entries(result.by_exchange || {}).map(([ex, n]) => `${ex} ${n}`).join(" · ")})</Detail>
              {Object.entries(result.totals || {}).map(([ex, t]) => (
                <Detail key={ex} label={`${ex} Buy / Sale`}>{money(t.buy_value)} / {money(t.sell_value)}</Detail>
              ))}
              <Detail label="Checks">Totals match the report</Detail>
              {result.bhavcopy && <Detail label="Bhavcopy" warn={Object.keys(result.bhavcopy.errors || {}).length > 0}>{bhavcopyText(result.bhavcopy)}</Detail>}
              {gaps.length > 0 && (
                <Detail label="No report for" warn>{gaps.map(([ex, list]) => `${ex}: ${list.map(formatDate).join(", ")}`).join(" · ")} (upload, unless a holiday)</Detail>
              )}
            </div>
            <DialogFooter><Button className="w-full sm:w-auto" onClick={onClose}>Done</Button></DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
