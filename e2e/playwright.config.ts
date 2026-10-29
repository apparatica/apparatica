// End-to-end tests against a running stand with a real worker (specs/09 §4.4, docs/stand.md).
//
//   just up && just e2e
//
// Environment:
//   E2E_BASE_URL: the site of the stand, http://localhost:8080 by default
//   E2E_BROWSER: Playwright channel of an installed browser, "chrome" by default ("msedge" on Windows)
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  // The checks share one worker of the stand; one at a time keeps their timing predictable.
  workers: 1,
  forbidOnly: !!process.env.CI,
  // A check compiles the solution with Verilator: tens of seconds, the first one longer.
  timeout: 4 * 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    channel: process.env.E2E_BROWSER ?? "chrome",
    locale: "ru-RU",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
});
