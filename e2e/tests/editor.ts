// The editor of a problem page in the e2e tests: the code goes into Monaco, a check starts from the
// toolbar.
import { readFileSync } from "node:fs";

import type { Page, Route } from "@playwright/test";

import { expect } from "./fixtures";

/** A file of a problem of the repository: `problems/<slug>/<file>`. */
export const problemFile = (slug: string, file: string) =>
  readFileSync(new URL(`../../problems/${slug}/${file}`, import.meta.url), "utf-8");

/** Replace the code in Monaco by a paste: typed text would be auto-indented on the way. */
export async function enterCode(page: Page, code: string) {
  await page.locator(".monaco-editor .view-lines").click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.evaluate((text) => {
    const data = new DataTransfer();
    data.setData("text/plain", text);
    const paste = new ClipboardEvent("paste", {
      clipboardData: data,
      bubbles: true,
      cancelable: true,
    });
    document.activeElement?.dispatchEvent(paste);
  }, code);
}

/** Start a check from the editor toolbar; return the code the API received. The body is read by
 * an interception: the CSRF repeat clones the request (web/src/lib/api/csrf.ts), a cloned body is
 * sent as a stream, and the browser does not report a stream to `waitForRequest`. */
export async function check(page: Page, kind: "Run" | "Submit"): Promise<string> {
  let code: string | undefined;
  const handler = async (route: Route) => {
    if (route.request().method() === "POST") {
      code ??= (route.request().postDataJSON() as { code: string }).code;
    }
    await route.continue();
  };
  await page.route("/api/v1/submissions", handler);
  try {
    await page.locator("button[aria-keyshortcuts]", { hasText: kind }).click();
    await expect.poll(() => code).toBeDefined();
    return code!;
  } finally {
    await page.unroute("/api/v1/submissions", handler);
  }
}
