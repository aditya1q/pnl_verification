import { useState } from "react";
import { Upload } from "lucide-react";
import Spinner from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { lossText } from "@/utils/format";

// Row of an import bar: description on the left, ImportControl on the right.
export const importBar = "flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2 text-xs text-muted-foreground shadow-xs";

// File picker button with busy / success / error messages, shared by the import bars.
// `onFiles(files)` resolves to { message, error } (both optional) or throws.
// On a throw, `err.partialMessage` (if set) is still shown next to the error.
export default function ImportControl({ label, busyLabel = "Importing…", accept, title, multiple = false, onFiles }) {
  const [state, setState] = useState({ busy: false, message: "", error: "" });

  async function handleChange(event) {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    if (!files.length) return;
    setState({ busy: true, message: "", error: "" });
    try {
      const result = (await onFiles(files)) || {};
      setState({ busy: false, message: result.message || "", error: result.error || "" });
    } catch (err) {
      setState({ busy: false, message: err.partialMessage || "", error: err.message });
    }
  }

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      {state.message && <span className="text-profit">{state.message}</span>}
      {state.error && <span className={lossText}>{state.error}</span>}
      <Button asChild variant="outline" size="sm" className="h-7 cursor-pointer text-xs" title={title}>
        <label aria-disabled={state.busy}>
          {state.busy ? <><Spinner /> {busyLabel}</> : <><Upload /> {label}</>}
          <input type="file" className="sr-only" accept={accept} multiple={multiple} disabled={state.busy} onChange={handleChange} />
        </label>
      </Button>
    </div>
  );
}
