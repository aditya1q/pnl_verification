import { cn } from "@/lib/utils";

// Pulsing placeholder block shown while data loads.
export default function Skeleton({ className }) {
  return <span aria-hidden="true" className={cn("block animate-pulse rounded-md bg-muted", className)} />;
}
