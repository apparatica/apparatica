// Scenario 2 of specs/09 §4.4: a guest signs in with a login link. The letter is caught by Mailpit
// of the stand and read through its API; the import of guest solutions comes in Ф4 (T4.5).
//
// E2E_MAILPIT_URL: Mailpit of the stand, http://localhost:8025 by default; empty skips the test
// (a site without Mailpit, such as staging).
import type { APIRequestContext } from "@playwright/test";

import { expectAccessible } from "./axe";
import { expect, test } from "./fixtures";

const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

type Summary = { ID: string };
type Message = { Subject: string; Text: string };

/** The login link of the letter sent to the address; waits for the letter. */
async function loginLink(request: APIRequestContext, address: string): Promise<string> {
  let found: Summary | undefined;
  await expect
    .poll(
      async () => {
        const search = await request.get(`${MAILPIT}/api/v1/search`, {
          params: { query: `to:"${address}"` },
        });
        expect(search.ok()).toBe(true);
        found = ((await search.json()) as { messages: Summary[] }).messages[0];
        return found;
      },
      { message: `a letter to ${address} in Mailpit` },
    )
    .toBeDefined();
  const message = (await (
    await request.get(`${MAILPIT}/api/v1/message/${found!.ID}`)
  ).json()) as Message;
  expect(message.Subject).toBe("Вход в Apparatica");
  const link = /\S+\/login\/email\/verify#token=\S+/.exec(message.Text)?.[0];
  expect(link, "the login link of the letter").toBeDefined();
  return link!;
}

test("a guest signs in with a login link from the letter", async ({ page, request }) => {
  test.skip(MAILPIT === "", "no Mailpit: E2E_MAILPIT_URL is empty");
  // A new address each run: a new account, and the limit of letters per address is not reached.
  const address = `e2e-${Date.now().toString(36)}@example.com`;
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
