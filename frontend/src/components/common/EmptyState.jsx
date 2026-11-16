import { Inbox, Loader2 } from "lucide-react";

// Placeholder shown instead of an empty table.
export default function EmptyState({ title, children, loading = false }) {
  const Icon = loading ? Loader2 : Inbox;
  return (
    <div className="flex min-h-[220px] flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-card p-6 text-center">
      <div className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
        <Icon className={loading ? "size-5 animate-spin" : "size-5"} />
      </div>
      <p className="text-sm font-semibold">{title}</p>
      {children && <p className="max-w-md text-sm text-muted-foreground">{children}</p>}
    </div>
  );
}
