import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import ErrorMessage from "@/components/common/ErrorMessage";
import Spinner from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const EMPTY = { current: "", next: "", repeat: "" };

export default function ChangePasswordDialog({ open, onClose }) {
  const { changePassword } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  function close() {
    if (busy) return;
    setForm(EMPTY); setError(""); setDone(false);
    onClose();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (form.next !== form.repeat) { setError("The new passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      await changePassword(form.current, form.next);
      setDone(true); setForm(EMPTY);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  const field = (key, label, autoComplete) => (
    <div className="grid gap-2">
      <Label htmlFor={`pw-${key}`}>{label}</Label>
      <Input id={`pw-${key}`} type="password" required autoComplete={autoComplete} value={form[key]} disabled={busy}
        onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-sm" showCloseButton={!busy}>
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Change password</DialogTitle>
            <DialogDescription>At least 8 characters. Your other signed-in browsers are signed out.</DialogDescription>
          </DialogHeader>
          {done ? <p className="text-sm text-profit">Password changed.</p> : (
            <>
              {field("current", "Current password", "current-password")}
              {field("next", "New password", "new-password")}
              {field("repeat", "Repeat new password", "new-password")}
            </>
          )}
          <ErrorMessage>{error}</ErrorMessage>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={busy}>{done ? "Close" : "Cancel"}</Button>
            {!done && <Button type="submit" disabled={busy}>{busy ? <><Spinner /> Saving…</> : "Change password"}</Button>}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
