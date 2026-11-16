import { useEffect, useState } from "react";

// Runs `load(signal)` whenever `deps` change and tracks { data, loading, error }.
// Pass `null` as `load` to skip loading (e.g. for a tab that is not shown).
export function useRemote(load, deps) {
  const [state, setState] = useState({ data: null, loading: false, error: "" });
  useEffect(() => {
    if (!load) { setState({ data: null, loading: false, error: "" }); return undefined; }
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    load(controller.signal)
      .then((data) => setState({ data, loading: false, error: "" }))
      .catch((err) => {
        if (err.name !== "AbortError") setState({ data: null, loading: false, error: err.message });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
