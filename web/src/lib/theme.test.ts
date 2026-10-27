import { afterEach, describe, expect, it } from "vitest";

import { clearThemeState, mockColorScheme } from "@/test/match-media";

import { applyTheme, parseTheme, THEME_SCRIPT, themeCookie } from "./theme";

const runScript = () => new Function(THEME_SCRIPT)();
const attribute = () => document.documentElement.dataset["theme"];

afterEach(clearThemeState);

describe("theme choice", () => {
  it("parses the cookie, defaulting to the system theme", () => {
    expect(parseTheme("dark")).toBe("dark");
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("system")).toBe("system");
    expect(parseTheme(undefined)).toBe("system");
    expect(parseTheme("sepia")).toBe("system");
  });

  it("keeps the choice for a year on the whole site", () => {
    expect(themeCookie("dark")).toBe("ap_theme=dark; Path=/; Max-Age=31536000; SameSite=Lax");
  });

  it("applies a choice to the page and the cookie", () => {
    mockColorScheme("dark");
    applyTheme("light");
    expect(attribute()).toBe("light");
    expect(document.cookie).toContain("ap_theme=light");
    applyTheme("system");
    expect(attribute()).toBe("dark");
  });
});

describe("the script before the first paint", () => {
  it("follows the system theme without an explicit choice", () => {
    const scheme = mockColorScheme("dark");
    runScript();
    expect(attribute()).toBe("dark");
    scheme.set("light");
    expect(attribute()).toBe("light");
  });

  it("leaves an explicit choice rendered by the server", () => {
    const scheme = mockColorScheme("dark");
    document.cookie = "ap_theme=light; Path=/";
    document.documentElement.dataset["theme"] = "light";
    runScript();
    scheme.set("dark");
    expect(attribute()).toBe("light");
  });

  it("treats the cookie value system as no choice", () => {
    mockColorScheme("light");
    document.cookie = "ap_theme=system; Path=/";
    runScript();
    expect(attribute()).toBe("light");
  });
});
