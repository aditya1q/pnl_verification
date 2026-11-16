import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// Busy indicator for buttons; takes the current text colour.
export default function Spinner({ className }) {
  return <Loader2 className={cn("animate-spin", className)} aria-hidden="true" />;
}
