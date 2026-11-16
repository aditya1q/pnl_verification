import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { headClass } from "@/components/common/DataTable";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Sortable column header. A column without a `key` renders as a plain header.
export default function SortHeader({ column, sort, onSort }) {
  const num = column.align === "right";
  if (!column.key) return <TableHead className={headClass(num)}>{column.label}</TableHead>;
  const active = sort.key === column.key;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead className={headClass(num)} aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(column.key)}
        className={cn("inline-flex cursor-pointer items-center gap-1 uppercase tracking-wide transition-colors hover:text-foreground",
          num && "flex-row-reverse", active && "text-foreground")}>
        {column.label}
        <Icon className={cn("size-3", !active && "opacity-50")} aria-hidden="true" />
      </button>
    </TableHead>
  );
}

// onSort handler: the same column flips direction, a new column starts ascending; goes back to page 0.
export function toggleSort(setSort, resetPage) {
  return (key) => {
    setSort((prev) => ({ key, dir: prev.key === key && prev.dir === "asc" ? "desc" : "asc" }));
    resetPage(0);
  };
}
