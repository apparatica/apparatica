"use client";

import { createContext, type ReactNode, use, useState, useSyncExternalStore } from "react";

import { applyTheme, type ResolvedTheme, type Theme } from "@/lib/theme";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

/** The theme chosen on this page: the guest menu and the command palette change it. */
export function ThemeProvider({ initial, children }: { initial: Theme; children: ReactNode }) {
  const [theme, set] = useState(initial);
  const setTheme = (next: Theme) => {
    applyTheme(next);
    set(next);
  };
  return <ThemeContext value={{ theme, setTheme }}>{children}</ThemeContext>;
}

export function useTheme(): ThemeState {
  const state = use(ThemeContext);
  if (state === null) throw new Error("useTheme outside ThemeProvider");
  return state;
}

function subscribeToTheme(listener: () => void): () => void {
  const observer = new MutationObserver(listener);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

/** The theme on screen: `data-theme` of <html>, which a choice and the OS (for "system") change.
 * Light on the server and while the page hydrates. For what CSS cannot colour, such as Monaco. */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(
    subscribeToTheme,
    () => (document.documentElement.dataset["theme"] === "dark" ? "dark" : "light"),
    () => "light",
  );
}
