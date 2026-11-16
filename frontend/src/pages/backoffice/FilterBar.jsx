import { RotateCcw } from "lucide-react";
import SegmentedControl from "@/components/common/SegmentedControl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Radix Select / ToggleGroup cannot use "" as a value, so "all" is this placeholder in the UI.
const ALL = "__all";
const EXCHANGES = [{ value: ALL, label: "All" }, { value: "NSE", label: "NSE" }, { value: "BSE", label: "BSE" }];

function Field({ id, title, children }) {
  return (
    <div className="grid min-w-0 flex-[1_1_140px] gap-1.5 sm:max-w-[200px]">
      <Label htmlFor={id} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</Label>
      {children}
    </div>
  );
}

function OptionSelect({ id, value, onChange, allLabel, options }) {
  return (
    <Select value={value || ALL} onValueChange={(next) => onChange(next === ALL ? "" : next)}>
      <SelectTrigger id={id} size="sm" className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

export default function FilterBar({ filters, options, onChange, onReset }) {
  const hasFilters = Object.values(filters).some(Boolean);
  return (
    <section className="flex shrink-0 flex-wrap items-end gap-3 rounded-xl border bg-card p-3 shadow-card" aria-label="P&L filters">
      <div className="grid gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Exchange</span>
        <SegmentedControl label="Exchange filter" options={EXCHANGES} value={filters.exchange || ALL}
          onChange={(value) => onChange("exchange", value === ALL ? "" : value)} />
      </div>
      <Field id="f-date" title="Specific date">
        <Input id="f-date" type="date" className="h-8" value={filters.date} onChange={(e) => onChange("date", e.target.value)} />
      </Field>
      <Field id="f-from" title="From">
        <Input id="f-from" type="date" className="h-8" value={filters.from} max={filters.to || undefined} onChange={(e) => onChange("from", e.target.value)} />
      </Field>
      <Field id="f-to" title="To">
        <Input id="f-to" type="date" className="h-8" value={filters.to} min={filters.from || undefined} onChange={(e) => onChange("to", e.target.value)} />
      </Field>
      <Field id="f-symbol" title="Trading symbol">
        <OptionSelect id="f-symbol" value={filters.symbol} onChange={(v) => onChange("symbol", v)} allLabel="All symbols" options={options.symbols} />
      </Field>
      <Field id="f-instrument" title="Instrument">
        <OptionSelect id="f-instrument" value={filters.instrument} onChange={(v) => onChange("instrument", v)} allLabel="All instruments" options={options.instruments} />
      </Field>
      <Button variant="ghost" size="sm" onClick={onReset} disabled={!hasFilters} className="text-muted-foreground">
        <RotateCcw /> Reset
      </Button>
    </section>
  );
}
