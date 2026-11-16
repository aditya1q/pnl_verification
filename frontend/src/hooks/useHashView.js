import { useEffect, useState } from "react";

export const VIEWS = { NET_POSITION: "netposition", BACKOFFICE: "backoffice" };

// "#backoffice?exchange=NSE&date=2026-11-12" -> { page: "backoffice", params }
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "");
  const [page = "", query = ""] = raw.split("?");
  return { page, params: new URLSearchParams(query) };
}

function viewFromHash() {
  return parseHash().page === VIEWS.BACKOFFICE ? VIEWS.BACKOFFICE : VIEWS.NET_POSITION;
}

// Current page, driven by the URL hash (#netposition / #backoffice, with optional ?params).
// `routeKey` changes when the hash is changed from outside the app (typed URL, Back / Forward),
// so the page can be remounted and re-read its parameters.
export function useHashView() {
  const [route, setRoute] = useState(() => ({ view: viewFromHash(), routeKey: 0 }));
  useEffect(() => {
    const onHashChange = () => setRoute((prev) => ({ view: viewFromHash(), routeKey: prev.routeKey + 1 }));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return route;
}

// The current page's URL parameters, as a plain object ({ exchange: "NSE", date: "2026-11-12" }).
export function readHashParams() {
  return Object.fromEntries(parseHash().params);
}

// Show `values` as the current page's URL parameters (empty values are left out).
// Uses replaceState: the address updates without adding a history entry or firing hashchange.
export function writeHashParams(view, values) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  }
  const query = params.toString();
  const hash = `#${view}${query ? `?${query}` : ""}`;
  if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
}
