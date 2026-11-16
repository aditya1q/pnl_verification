import { useCallback, useEffect, useState } from "react";
import { KeyRound, UserPlus } from "lucide-react";
import { postJson, requestJson } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import ErrorMessage from "@/components/common/ErrorMessage";
import Spinner from "@/components/common/Spinner";
import ToneBadge from "@/components/common/ToneBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import CreateUserDialog from "./CreateUserDialog";
import { RoleSelect, USERS_CHANGED } from "./roles";

function when(value) {
  return value ? new Date(`${value}Z`).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyUser, setBusyUser] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    requestJson("/api/users").then(setUsers).catch((err) => setError(err.message));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    window.addEventListener(USERS_CHANGED, load);
    return () => window.removeEventListener(USERS_CHANGED, load);
  }, [load]);

  async function change(username, body, done) {
    setBusyUser(username); setError(""); setMessage("");
    try {
      await postJson(`/api/users/${encodeURIComponent(username)}`, body, "PATCH");
      setMessage(done);
      load();
    } catch (err) { setError(err.message); } finally { setBusyUser(null); }
  }

  function resetPassword(username) {
    const password = window.prompt(`New password for ${username} (at least 8 characters). They will be signed out.`);
    if (password) change(username, { password }, `Password changed for ${username}; their sessions were signed out.`);
  }

  return (
    <div className="flex flex-col gap-3 sm:min-h-0">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="font-display text-lg font-extrabold">Users</h1>
          <p className="text-xs text-muted-foreground">Who can sign in and what they can do. A change to a user signs them out of every browser.</p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}><UserPlus /> Create user</Button>
      </div>
      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      {message && <p className="text-xs text-profit">{message}</p>}
      <ErrorMessage>{error}</ErrorMessage>
      <div className="overflow-auto rounded-xl border bg-card shadow-card sm:min-h-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last sign-in</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!users && <TableRow><TableCell colSpan={6} className="text-muted-foreground"><Spinner className="inline size-4" /> Loading…</TableCell></TableRow>}
            {users?.map((u) => {
              const self = u.username.toLowerCase() === me?.username.toLowerCase();
              const busy = busyUser === u.username;
              return (
                <TableRow key={u.username}>
                  <TableCell className="font-semibold">{u.username}{self && <span className="ml-1.5 text-xs font-normal text-muted-foreground">(you)</span>}</TableCell>
                  <TableCell>
                    <RoleSelect value={u.role} disabled={busy}
                      onChange={(role) => change(u.username, { role }, `${u.username} is now ${role}.`)} />
                  </TableCell>
                  <TableCell>{u.active ? <ToneBadge tone="long">Active</ToneBadge> : <ToneBadge tone="short">Disabled</ToneBadge>}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{when(u.last_login_at)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{when(u.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      <Button variant="ghost" size="sm" className="h-7 text-xs" disabled={busy} onClick={() => resetPassword(u.username)}>
                        <KeyRound className="size-3" /> Reset password
                      </Button>
                      {!self && (
                        <Button variant="ghost" size="sm" className="h-7 text-xs" disabled={busy}
                          onClick={() => change(u.username, { active: !u.active }, `${u.username} ${u.active ? "disabled" : "enabled"}.`)}>
                          {u.active ? "Disable" : "Enable"}
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
