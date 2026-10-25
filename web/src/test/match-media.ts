import { vi } from "vitest";

/** A controllable prefers-color-scheme: jsdom has no matchMedia. */
export function mockColorScheme(initial: "light" | "dark") {
  let dark = initial === "dark";
  const listeners = new Set<() => void>();
  const query = {
    get matches() {
      return dark;
    },
    media: "(prefers-color-scheme: dark)",
    addEventListener: (_: "change", listener: () => void) => listeners.add(listener),
    removeEventListener: (_: "change", listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", () => query);
  return {
    set(scheme: "light" | "dark") {
      dark = scheme === "dark";
      listeners.forEach((listener) => listener());
    },
  };
}

export function clearThemeState() {
  document.cookie = "ap_theme=; Path=/; Max-Age=0";
  delete document.documentElement.dataset["theme"];
  vi.unstubAllGlobals();
}
