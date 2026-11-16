import { useState } from "react";
import { UserPlus } from "lucide-react";
import { postJson } from "@/api/client";
import ErrorMessage from "@/components/common/ErrorMessage";
import Spinner from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RoleSelect, ROLES, USERS_CHANGED } from "./roles";

const EMPTY = { username: "", password: "", repeat: "", role: "viewer" };

export default function CreateUserDialog({ open, onClose }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);

  const set = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  function close() {
    if (busy) return;
    setForm(EMPTY); setError(""); setCreated(null);
    onClose();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (form.password !== form.repeat) { setError("The passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      const user = await postJson("/api/users", { username: form.username.trim(), password: form.password, role: form.role });
      setCreated(user); setForm(EMPTY);
      window.dispatchEvent(new Event(USERS_CHANGED));
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  const hint = ROLES.find((r) => r.value === form.role)?.hint;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-sm" showCloseButton={!busy}>
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Create user</DialogTitle>
            <DialogDescription>They sign in with this username and password and can change the password later.</DialogDescription>
          </DialogHeader>
          {created ? (
            <p className="text-sm text-profit">User <strong>{created.username}</strong> created as {created.role}.</p>
          ) : (
            <>
              <div className="grid gap-2">
                <Label htmlFor="cu-username">Username</Label>
                <Input id="cu-username" required autoComplete="off" autoFocus value={form.username} disabled={busy}
                  pattern="[A-Za-z0-9._\-]{3,32}" title="3 to 32 letters, digits, dot, dash or underscore" onChange={set("username")} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cu-password">Password</Label>
                <Input id="cu-password" type="password" required minLength={8} autoComplete="new-password"
                  value={form.password} disabled={busy} onChange={set("password")} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cu-repeat">Repeat password</Label>
                <Input id="cu-repeat" type="password" required minLength={8} autoComplete="new-password"
                  value={form.repeat} disabled={busy} onChange={set("repeat")} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cu-role">Role</Label>
                <RoleSelect id="cu-role" className="w-full" value={form.role} disabled={busy}
                  onChange={(role) => setForm((prev) => ({ ...prev, role }))} />
                <p className="text-xs text-muted-foreground">{hint}</p>
              </div>
            </>
          )}
          <ErrorMessage>{error}</ErrorMessage>
          <DialogFooter>
            {created ? (
              <>
                <Button type="button" variant="outline" onClick={() => setCreated(null)}>Create another</Button>
                <Button type="button" onClick={close}>Done</Button>
              </>
            ) : (
              <>
                <Button type="button" variant="outline" onClick={close} disabled={busy}>Cancel</Button>
                <Button type="submit" disabled={busy}>{busy ? <><Spinner /> Creating…</> : <><UserPlus /> Create user</>}</Button>
              </>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
