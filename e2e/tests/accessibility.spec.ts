// axe on the key screens of phase 1 in both themes, wide and on a phone (specs/09 §4.4); the problem
// page with a verdict is checked by the guest scenario.
import { devices, expect, test } from "@playwright/test";

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

    test.describe("phone", () => {
      // A device of the list without its browser type, which a group cannot change.
      const { defaultBrowserType: _, ...phone } = devices["Pixel 7"];
      test.use(phone);

      test("the catalogue", async ({ page }) => {
        await page.goto("/problems");
        await expect(page.getByRole("list", { name: "Список задач" })).toBeVisible();
        await expectAccessible(page);
      });

      test("the problem page", async ({ page }) => {
        await page.goto("/problems/mux4");
        await expect(page.getByText("Решать удобнее на компьютере")).toBeVisible();
        await expect(page.locator(".monaco-editor")).toHaveCount(0);
        await expectAccessible(page);
      });
    });
  });
}
