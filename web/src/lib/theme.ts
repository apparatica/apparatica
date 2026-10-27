// Colour theme (specs/08 §2): system by default; an explicit choice is kept in a cookie so that the
// server renders <html data-theme> and the page does not flash. For "system" the server cannot know
// the answer: THEME_SCRIPT sets the attribute before the first paint and follows OS changes.

export const THEME_COOKIE = "ap_theme";
export const THEMES = ["system", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];
export type ResolvedTheme = Exclude<Theme, "system">;

const ONE_YEAR_S = 60 * 60 * 24 * 365;

export function parseTheme(value: string | undefined): Theme {
  return THEMES.find((theme) => theme === value) ?? "system";
}

export function themeCookie(theme: Theme): string {
  return `${THEME_COOKIE}=${theme}; Path=/; Max-Age=${ONE_YEAR_S}; SameSite=Lax`;
}

export function systemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Applies a choice in the browser: the cookie for the next requests, the attribute for now. */
export function applyTheme(theme: Theme): void {
  document.cookie = themeCookie(theme);
  document.documentElement.dataset["theme"] = theme === "system" ? systemTheme() : theme;
}

// Inline in <head>, so it runs before the first paint. Kept in sync with THEME_COOKIE (a test runs it).
export const THEME_SCRIPT = `(function () {
  try {
    var explicit = function () { return /(?:^|; )${THEME_COOKIE}=(light|dark)(?:;|$)/.test(document.cookie); };
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    var apply = function () {
      if (!explicit()) document.documentElement.dataset.theme = query.matches ? "dark" : "light";
    };
    apply();
    query.addEventListener("change", apply);
  } catch (error) {}
})();`;
