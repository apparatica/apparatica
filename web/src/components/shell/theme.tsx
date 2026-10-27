"use client";

import { createContext, type ReactNode, use, useState } from "react";

import { applyTheme, type Theme } from "@/lib/theme";

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
