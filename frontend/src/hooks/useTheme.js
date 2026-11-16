import { useCallback, useEffect, useState } from "react";

// Light / dark / system theme, remembered per browser. index.html applies it before first paint.
const KEY = "theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

function readTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

function apply(theme) {
  const dark = theme === "dark" || (theme === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme() {
  const [theme, setThemeState] = useState(readTheme);

  useEffect(() => {
    apply(theme);
    if (theme !== "system") return undefined;
    const query = media();
    const onChange = () => apply("system");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next) => {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch { /* storage blocked: still applies for this visit */ }
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
