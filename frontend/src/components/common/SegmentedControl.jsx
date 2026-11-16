import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

// Single-choice button group (e.g. NSE / BSE). `options` is [{ value, label }].
// Clicking the active option keeps it selected instead of clearing it.
export default function SegmentedControl({ value, onChange, options, label, className }) {
  return (
    <ToggleGroup type="single" variant="outline" size="sm" value={value} aria-label={label}
      onValueChange={(next) => { if (next) onChange(next); }}
      className={cn("bg-card shadow-xs", className)}>
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value}
          className="px-3 text-xs font-semibold data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
