// axe on the key screens of phase 1 in both themes (specs/09 §4.4); the problem page with a verdict
// is checked by the guest scenario.
import { expect, test } from "@playwright/test";

import { expectAccessible } from "./axe";

for (const theme of ["light", "dark"] as const) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ context, baseURL }) => {
      await context.addCookies([{ name: "ap_theme", value: theme, url: baseURL! }]);
    });

    test("the catalogue", async ({ page }) => {
      await page.goto("/problems");
      await expect(page.getByRole("link", { name: /Мультиплексор 4:1/ })).toBeVisible();
      await expectAccessible(page);
    });

    test("the problem page", async ({ page }) => {
      await page.goto("/problems/mux4");
      await expect(page.locator(".monaco-editor .view-lines")).toBeVisible();
      await expectAccessible(page);
    });
  });
}
