import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Soft coloured badges for option type, side, C/F and price source.
const TONES = {
  call: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/60 dark:text-blue-300",
  put: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/60 dark:text-orange-300",
  long: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300",
  short: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300",
  cf: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/60 dark:text-violet-300",
  close: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-300",
  warn: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300",
  neutral: "border-border bg-muted text-muted-foreground",
};

export default function ToneBadge({ tone = "neutral", className, ...props }) {
  return <Badge variant="outline" className={cn("rounded-md px-1.5 py-0 text-[11px] font-semibold", TONES[tone], className)} {...props} />;
}
