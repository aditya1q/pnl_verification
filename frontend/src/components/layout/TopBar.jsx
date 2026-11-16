import { BarChart3, LayoutList } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VIEWS } from "@/hooks/useHashView";
import { cn } from "@/lib/utils";

const PAGES = [
  { view: VIEWS.NET_POSITION, href: "#netposition", label: "Net Position", icon: LayoutList },
  { view: VIEWS.BACKOFFICE, href: "#backoffice", label: "Backoffice P&L", icon: BarChart3 },
];

export default function TopBar({ view }) {
  return (
    <header className="shrink-0 border-b bg-card">
      <div className="mx-auto flex h-14 w-full max-w-[95%] items-center gap-3 px-4">
        <div className="grid size-8 place-items-center rounded-lg bg-primary font-display text-xs font-extrabold text-primary-foreground">TD</div>
        <div className="leading-tight">
          <div className="font-display text-sm font-extrabold">Trader Data</div>
          <div className="hidden text-[11px] text-muted-foreground sm:block">NSE / BSE F&amp;O back office</div>
        </div>
        <nav className="ml-auto flex items-center gap-1 sm:ml-6" aria-label="Pages">
          {PAGES.map(({ view: target, href, label, icon: Icon }) => {
            const active = view === target;
            return (
              <Button key={target} asChild variant={active ? "secondary" : "ghost"} size="sm"
                className={cn("text-xs font-semibold", !active && "text-muted-foreground")}>
                <a href={href} aria-current={active ? "page" : undefined}><Icon /> {label}</a>
              </Button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
