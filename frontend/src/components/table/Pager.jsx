import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { count } from "@/utils/format";

// Footer of a DataTable: row count and Previous / Next.
export default function Pager({ page, total, pageSize, loading, onPage, label }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex shrink-0 flex-col items-start justify-between gap-2 border-t bg-card px-3 py-2 text-xs text-muted-foreground sm:flex-row sm:items-center">
      <span>{loading ? "Loading…" : `${count(total)} ${label}`}</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => onPage(page - 1)} disabled={page === 0 || loading}>
          <ChevronLeft /> Previous
        </Button>
        <span className="tabular-nums">Page {Math.min(page + 1, pageCount)} of {pageCount}</span>
        <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => onPage(page + 1)} disabled={page + 1 >= pageCount || loading}>
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
