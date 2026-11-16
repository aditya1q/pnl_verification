import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Soft coloured badges for option type, side, C/F and price source.
const TONES = {
  call: "border-blue-200 bg-blue-50 text-blue-700",
  put: "border-orange-200 bg-orange-50 text-orange-700",
  long: "border-emerald-200 bg-emerald-50 text-emerald-700",
  short: "border-rose-200 bg-rose-50 text-rose-700",
  cf: "border-violet-200 bg-violet-50 text-violet-700",
  close: "border-sky-200 bg-sky-50 text-sky-700",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  neutral: "border-border bg-muted text-muted-foreground",
};

export default function ToneBadge({ tone = "neutral", className, ...props }) {
  return <Badge variant="outline" className={cn("rounded-md px-1.5 py-0 text-[11px] font-semibold", TONES[tone], className)} {...props} />;
}
