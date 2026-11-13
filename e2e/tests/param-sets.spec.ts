// Parameter sets (ADR-0014, T3a.7): a solution with a hard-coded width passes Run, which checks the
// primary set only, and fails Submit at the extra set the width breaks, named in the verdict.
import { expectAccessible } from "./axe";
import { check, enterCode, problemFile } from "./editor";
import { expect, test } from "./fixtures";

// The mutant selects through an 8-bit signal: right at WIDTH = 8 (primary) and 1 (narrow), the
// high bits are lost at WIDTH = 32 (wide), which the hidden tests catch.
const FIXED_WIDTH = problemFile("mux4", "mutants/m05_fixed_width.sv");

test("a hard-coded width passes Run and fails Submit at the extra set", async ({ page }) => {
  await page.goto("/problems/mux4");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Мультиплексор 4:1");
  const results = page.getByRole("region", { name: "Результаты проверки" });

  await test.step("Run checks the primary set only and passes", async () => {
    await enterCode(page, FIXED_WIDTH);
    expect(await check(page, "Run")).toBe(FIXED_WIDTH);
    await expect(results).toContainText("Открытые тесты пройдены", { timeout: 3 * 60_000 });
  });

  await test.step("Submit fails at the set wide", async () => {
    expect(await check(page, "Submit")).toBe(FIXED_WIDTH);
    await expect(results).toContainText("Неверный ответ · набор wide: WIDTH=32", {
      timeout: 3 * 60_000,
    });
    await expect(results).toContainText(/Упал скрытый тест \d из 2/);
  });

  await test.step("the page with the verdict is accessible", async () => {
    await expectAccessible(page);
  });
});
