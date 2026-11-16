import { useEffect, useState } from "react";
import { FileUp } from "lucide-react";
import { uploadFile } from "@/api/client";
import ErrorMessage from "@/components/common/ErrorMessage";
import Spinner from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

// Upload dialog for the broker's daily net position report. Calls onImported(result) on success.
export default function UploadModal({ open, onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (open) { setFile(null); setError(""); setBusy(false); } }, [open]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file) { setError("Choose the day's net position file."); return; }
    setBusy(true); setError("");
    try {
      onImported(await uploadFile("/api/net-positions", file));
    } catch (err) {
      setError(err.message || "Unable to import the file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onClose(); }}>
      <DialogContent className="sm:max-w-md" showCloseButton={!busy}>
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Upload net position</DialogTitle>
            <DialogDescription>The broker's daily net position report. The date is read from the file; NSE and BSE rows are both imported.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="np-file">Report file</Label>
            <label htmlFor="np-file"
              className={cn("flex cursor-pointer items-center gap-3 rounded-lg border border-dashed p-4 transition-colors hover:bg-accent",
                file ? "border-primary/40 bg-accent" : "bg-muted/40")}>
              <input id="np-file" type="file" accept=".csv,.xls,.txt,.prn" className="sr-only"
                onChange={(event) => setFile(event.target.files?.[0] || null)} />
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary"><FileUp className="size-5" /></span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium">{file ? file.name : "Choose net position file"}</span>
                <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1024).toFixed(1)} KB` : "CSV, XLS or TXT, e.g. NETPOSS02112026_FO_B-117.csv"}</span>
              </span>
            </label>
            <p className="text-xs text-muted-foreground">Re-uploading a day replaces it. Days on or before the Carry Forward date are refused.</p>
          </div>
          <ErrorMessage>{error}</ErrorMessage>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button type="submit" disabled={busy || !file}>{busy ? <><Spinner /> Importing…</> : "Import file"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
