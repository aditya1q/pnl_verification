import { useState } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import ErrorMessage from "@/components/common/ErrorMessage";
import Spinner from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const { login, notice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center bg-background p-4">
      <form onSubmit={handleSubmit} className="grid w-full max-w-sm gap-5 rounded-xl border bg-card p-6 shadow-card">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg bg-primary font-display text-xs font-extrabold text-primary-foreground">TD</div>
          <div className="leading-tight">
            <h1 className="font-display text-base font-extrabold">Trader Data</h1>
            <p className="text-xs text-muted-foreground">Sign in to the NSE / BSE F&amp;O back office</p>
          </div>
        </div>
        {notice && !error && <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">{notice}</p>}
        <div className="grid gap-2">
          <Label htmlFor="login-username">Username</Label>
          <Input id="login-username" autoComplete="username" autoFocus required value={username}
            onChange={(e) => setUsername(e.target.value)} disabled={busy} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="login-password">Password</Label>
          <Input id="login-password" type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} disabled={busy} />
        </div>
        <ErrorMessage>{error}</ErrorMessage>
        <Button type="submit" disabled={busy || !username.trim() || !password}>
          {busy ? <><Spinner /> Signing in…</> : <><LogIn /> Sign in</>}
        </Button>
      </form>
    </div>
  );
}
