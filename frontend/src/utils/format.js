import { MONTHS_SHORT } from "./dates.js";

export function money(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function price(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

// Quantity with Indian digit grouping; a missing value shows "—".
export function quantity(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("en-IN");
}

// Like quantity, but a missing value counts as 0 (for totals and counters).
export function count(value) {
  return Number(value || 0).toLocaleString("en-IN");
}

// Tailwind class for a profit (green) or loss (red) figure. Combine with cn() and put it
// last so it overrides any other text colour.
export function pnlClass(value) {
  if (value > 0) return "text-profit";
  if (value < 0) return "text-loss";
  return "";
}

// Class for text that is always shown in the loss / warning colour.
export const lossText = "text-loss";

// "2026-11-02" -> "02 Nov 2026"; a missing value shows "—".
export function formatDay(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return `${day} ${MONTHS_SHORT[Number(month) - 1] ?? month} ${year}`;
}

// Like formatDay, but a missing value gives "".
export function formatDate(value) {
  return value ? formatDay(value) : "";
}

// "2026-11" -> "Nov 2026"
export function formatMonth(value) {
  if (!value) return "—";
  const [year, month] = String(value).split("-");
  return `${MONTHS_SHORT[Number(month) - 1] ?? month} ${year}`;
}
