import { vi } from "vitest";

import { PHONE_QUERY } from "@/lib/viewport";

/** Media queries whose answers a test sets: jsdom has no matchMedia. Others never match. */
function mockMedia(media: string, initial: boolean) {
  let matches = initial;
  const listeners = new Set<() => void>();
  const query = {
    get matches() {
      return matches;
    },
    media,
    addEventListener: (_: "change", listener: () => void) => listeners.add(listener),
    removeEventListener: (_: "change", listener: () => void) => listeners.delete(listener),
  };
  const other = window.matchMedia;
  vi.stubGlobal("matchMedia", (asked: string) => (asked === media ? query : other(asked)));
  return {
    set(next: boolean) {
      matches = next;
      listeners.forEach((listener) => listener());
    },
  };
}

/** A controllable prefers-color-scheme. */
export function mockColorScheme(initial: "light" | "dark") {
  const query = mockMedia("(prefers-color-scheme: dark)", initial === "dark");
  return { set: (scheme: "light" | "dark") => query.set(scheme === "dark") };
}

/** A window as narrow as a phone (usePhone); undone by vi.unstubAllGlobals(). */
export function mockPhone(initial = true) {
  return mockMedia(PHONE_QUERY, initial);
}

export function clearThemeState() {
  document.cookie = "ap_theme=; Path=/; Max-Age=0";
  delete document.documentElement.dataset["theme"];
  vi.unstubAllGlobals();
}
