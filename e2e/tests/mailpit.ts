// The login with a link from a letter in the e2e tests. Letters of the stand are caught by Mailpit
// and read through its API.
//
// E2E_MAILPIT_URL: Mailpit of the stand, http://localhost:8025 by default; empty means none (a site
// without Mailpit, such as staging), and the tests that sign in are skipped.
import type { APIRequestContext, Page } from "@playwright/test";

import { expect } from "./fixtures";

export const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

type Summary = { ID: string };
type Message = { Subject: string; Text: string };

/** A new address each run: a new account, and the limit of letters per address is not reached. */
export const newAddress = () =>
  `e2e-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}@example.com`;

/** The login link of the letter sent to the address; waits for the letter. */
export async function loginLink(request: APIRequestContext, address: string): Promise<string> {
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

/** Sign in a new account with a link from the letter and come back to `next`; the nick of the
 * account. */
export async function signIn(page: Page, request: APIRequestContext, next: string) {
  const address = newAddress();
  await page.goto(`/login?next=${next}`);
  await page.getByRole("textbox", { name: "Почта" }).fill(address);
  await page.getByRole("button", { name: "Получить ссылку для входа" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Проверьте почту" })).toBeVisible();
  await page.goto(await loginLink(request, address));
  await expect(page).toHaveURL(next);
  await expect(page.getByRole("banner").getByRole("button", { name: /^user-/ })).toBeVisible();
  // The menu button has the initial of the avatar too; the link to the profile has the nick alone.
  const profile = page.getByRole("navigation", { name: "Разделы" }).getByRole("link", {
    name: "Профиль",
  });
  const nick = /^\/u\/([^/?#]+)$/.exec((await profile.getAttribute("href")) ?? "")?.[1];
  expect(nick, "the nick in the link to the profile").toBeDefined();
  return decodeURIComponent(nick!);
}
