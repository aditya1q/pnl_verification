export const EMPTY_FILTERS = { exchange: "", date: "", from: "", to: "", symbol: "", instrument: "" };

const EXCHANGES = ["NSE", "BSE"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Filters from the URL (#backoffice?exchange=NSE&date=2026-11-12). Invalid values are ignored;
// a specific date wins over From / To, like in the filter bar.
export function filtersFromUrl(params) {
  const exchange = String(params.exchange || "").toUpperCase();
  const date = (value) => (DATE_RE.test(value || "") ? value : "");
  const filters = {
    exchange: EXCHANGES.includes(exchange) ? exchange : "",
    date: date(params.date),
    from: date(params.from),
    to: date(params.to),
    symbol: params.symbol || "",
    instrument: params.instrument || "",
  };
  if (filters.date) { filters.from = ""; filters.to = ""; }
  return filters;
}

// URL parameters for the filters; "All" exchanges shows as exchange=ALL.
export function filtersToUrl(filters) {
  return { ...filters, exchange: filters.exchange || "ALL" };
}

// API query parameters for the filter bar. A specific date (or `overrideDate`) wins over From/To.
export function filterParams(filters, overrideDate) {
  const params = new URLSearchParams();
  if (filters.exchange) params.set("exchange", filters.exchange);
  const day = overrideDate || filters.date;
  if (day) {
    params.set("date_from", day); params.set("date_to", day);
  } else {
    if (filters.from) params.set("date_from", filters.from);
    if (filters.to) params.set("date_to", filters.to);
  }
  if (filters.symbol) params.set("symbol", filters.symbol);
  if (filters.instrument) params.set("instrument", filters.instrument);
  return params;
}

// Filter update rules: a specific date clears From/To and vice versa; a new exchange clears symbol/instrument.
export function applyFilter(prev, name, value) {
  const next = { ...prev, [name]: value };
  if (name === "date" && value) { next.from = ""; next.to = ""; }
  if ((name === "from" || name === "to") && value) next.date = "";
  if (name === "exchange") { next.symbol = ""; next.instrument = ""; }
  return next;
}
