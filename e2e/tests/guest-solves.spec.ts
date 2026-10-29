// Scenario 1 of specs/09 §4.4: a guest solves a problem. Run with a mistake → the waveform of the
// failure → the fix → Submit → Accepted, judged by the worker of the stand.
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { expectAccessible } from "./axe";

const problem = (file: string) =>
  readFileSync(new URL(`../../problems/mux4/${file}`, import.meta.url), "utf-8");
// The mutant swaps inputs 2 and 3: the first open test catches it.
const MISTAKE = problem("mutants/m01_swapped_inputs.sv");
const SOLUTION = problem("reference/mux4.sv");

/** Replace the code in Monaco by a paste: typed text would be auto-indented on the way. */
async function enterCode(page: Page, code: string) {
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

/** Start a check from the editor toolbar; return the code the API received. */
async function check(page: Page, kind: "Run" | "Submit"): Promise<string> {
  const request = page.waitForRequest(
    (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/v1/submissions",
  );
  await page.locator("button[aria-keyshortcuts]", { hasText: kind }).click();
  return ((await request).postDataJSON() as { code: string }).code;
}

test("a guest fixes a wrong answer with the waveform and gets Accepted", async ({ page }) => {
  await page.goto("/problems/mux4");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Мультиплексор 4:1");
  const results = page.getByRole("region", { name: "Результаты проверки" });
  await expect(results).toContainText("Результатов пока нет");

  await test.step("Run with a mistake fails an open test", async () => {
    await enterCode(page, MISTAKE);
    expect(await check(page, "Run")).toBe(MISTAKE);
    await expect(results).toContainText("Неверный ответ · Run на открытых тестах", {
      timeout: 3 * 60_000,
    });
    await expect(results).toContainText("Тест «каждый вход по очереди» упал на такте");
  });

  await test.step("the waveform of the failure opens in the viewer", async () => {
    await results.getByRole("button", { name: "Показать на диаграмме" }).first().click();
    await expect(results.getByRole("tab", { name: "Временные диаграммы" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // `normal`: the FST came from the storage and the viewer in its frame showed it.
    await expect(results.getByRole("region", { name: "Волны" })).toHaveAttribute(
      "data-state",
      "normal",
      { timeout: 60_000 },
    );
    await expect(results.getByTitle("Просмотрщик временных диаграмм")).toBeVisible();
  });

  await test.step("the fixed solution is accepted on Submit", async () => {
    await enterCode(page, SOLUTION);
    expect(await check(page, "Submit")).toBe(SOLUTION);
    await expect(results).toContainText("Принято", { timeout: 3 * 60_000 });
    await expect(results).toContainText("Все этапы пройдены, задача решена.");
  });

  await test.step("the page with the verdict is accessible", async () => {
    await expectAccessible(page);
  });
});
