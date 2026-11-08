// Scenario 2 of specs/09 §4.4: a guest signs in with a login link. The letter is caught by Mailpit
// of the stand and read through its API; the import of guest solutions comes in Ф4 (T4.5).
//
// E2E_MAILPIT_URL: Mailpit of the stand, http://localhost:8025 by default; empty skips the test
// (a site without Mailpit, such as staging).
import { expectAccessible } from "./axe";
import { expect, test } from "./fixtures";
import { loginLink, MAILPIT, newAddress } from "./mailpit";

test("a guest signs in with a login link from the letter", async ({ page, request }) => {
  test.skip(MAILPIT === "", "no Mailpit: E2E_MAILPIT_URL is empty");
  const address = newAddress();
  const header = page.getByRole("banner");

  await test.step("the login page opens from the header of a problem", async () => {
    await page.goto("/problems/mux4");
    await expect(header).toContainText("Гость");
    await header.getByRole("link", { name: "Войти" }).click();
    await expect(page).toHaveURL("/login?next=/problems/mux4");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Войти в Apparatica");
    await expectAccessible(page);
  });

  await test.step("the link is sent to the address", async () => {
    await page.getByRole("textbox", { name: "Почта" }).fill(address);
    await page.getByRole("button", { name: "Получить ссылку для входа" }).click();
    const sent = page.getByRole("status").filter({ hasText: "Проверьте почту" });
    await expect(sent).toContainText(address);
  });

  const link = await test.step("the letter has the link", () => loginLink(request, address));

  await test.step("the link signs in and returns to the problem", async () => {
    await page.goto(link);
    await expect(page).toHaveURL("/problems/mux4");
    await expect(header.getByRole("button", { name: /^user-/ })).toBeVisible();
    await expect(page.getByText("Гостевой режим")).toBeHidden();
  });

  await test.step("the settings show the address of the account", async () => {
    await page.goto("/settings");
    await expect(page.getByRole("main")).toContainText(address);
  });

  await test.step("the link works once", async () => {
    await page.goto(link);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ссылка не подходит");
    await expectAccessible(page);
  });

  await test.step("logout makes the browser a guest again", async () => {
    await page.goto("/problems/mux4");
    await header.getByRole("button", { name: /^user-/ }).click();
    await page.getByRole("menuitem", { name: "Выйти" }).click();
    await expect(header).toContainText("Гость");
    await expect(header.getByRole("link", { name: "Войти" })).toBeVisible();
  });
});
