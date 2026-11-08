// Scenarios 3 and 4 of specs/09 §4.4 for a user: an accepted Submit takes a place on the leaderboard
// of the problem (FR-LB-01), and the solution, public now, is shared by its short link with the OG
// picture (FR-SOL-01, FR-SHR-01..03). A guest's solutions do not rank, so a new account signs in
// with a link from the letter; without Mailpit (staging) the test is skipped.
//
// The stand keeps its data between runs: the reference of `mux4` from an earlier run is the same
// solution, and the new one shares its place (an AST duplicate). The place is read off the
// verdict, not assumed.
import { expectAccessible } from "./axe";
import { check, enterCode, problemFile } from "./editor";
import { expect, test } from "./fixtures";
import { MAILPIT, signIn } from "./mailpit";
import { expectLinkCard, expectShareDialog } from "./share";

const SOLUTION = problemFile("mux4", "reference/mux4.sv");

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("a user's accepted Submit takes a place and is shared", async ({ page, request }) => {
  test.skip(MAILPIT === "", "no Mailpit: E2E_MAILPIT_URL is empty");
  const nick = await test.step("a new account signs in", () =>
    signIn(page, request, "/problems/mux4"));
  const results = page.getByRole("region", { name: "Результаты проверки" });

  const { rank, total } = await test.step("Submit is accepted with a place", async () => {
    await enterCode(page, SOLUTION);
    expect(await check(page, "Submit")).toBe(SOLUTION);
    const title = results.getByText(/^Принято · место \d+ из \d+$/);
    await expect(title).toBeVisible({ timeout: 3 * 60_000 });
    await expect(results).toContainText(/[Рр]ешение стало публичным/);
    const [, place, of] = /место (\d+) из (\d+)/.exec(await title.innerText())!;
    return { rank: Number(place), total: Number(of) };
  });

  const link = await test.step("«Поделиться» gives the short link of the solution", async () => {
    await results.getByRole("button", { name: "Поделиться" }).click();
    const dialog = page.getByRole("dialog", { name: "Поделиться решением" });
    const preview = dialog.getByTestId("share-preview");
    await expect(preview).toContainText("Мультиплексор 4:1");
    await expect(preview).toContainText(`${rank} из ${total} · ${nick}`);
    const url = await expectShareDialog(page, dialog);
    expect(new URL(url).pathname).toMatch(/^\/s\/[0-9A-Za-z]+$/);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    return url;
  });

  await test.step("the leaderboard shows the place of the user", async () => {
    await results.getByRole("link", { name: "Смотреть рейтинг" }).click();
    await expect(page).toHaveURL(/^[^?#]*\/problems\/mux4\/leaderboard\b/);
    await expect(page.getByText(`Ваше решение · ${rank} место`)).toBeVisible();
    const row = page.locator("#me");
    await expect(row).toContainText(nick);
    await expect(row.getByRole("rowheader")).toHaveText(String(rank));
    await expectAccessible(page);
  });

  await test.step("the short link leads to the public solution with its card", async () => {
    const redirect = await request.get(link, { maxRedirects: 0 });
    expect(redirect.status()).toBe(301);
    expect(redirect.headers()["location"]).toMatch(/^\/solutions\/[0-9a-f-]{36}$/);

    await page.goto(link);
    await expect(page).toHaveURL(/\/solutions\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("main")).toContainText(nick);
    expect(await expectLinkCard(page, request)).toBe(`Решение ${nick} · Мультиплексор 4:1`);
    await expect(page.locator('meta[property="og:description"]')).toHaveAttribute(
      "content",
      new RegExp(`место ${rank} из ${total}`),
    );
    await expectAccessible(page);
  });
});
