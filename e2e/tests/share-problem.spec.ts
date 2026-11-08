// Scenario 4 of specs/09 §4.4 for a problem: «Поделиться» in the header of the statement and the
// card of the link with the OG picture (FR-SHR-01, FR-SHR-02). The solution of a user is shared in
// ranked-submit.spec.ts.
import { expectAccessible } from "./axe";
import { expect, test } from "./fixtures";
import { expectLinkCard, expectShareDialog } from "./share";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("a guest shares a problem with its link card", async ({ page, request }) => {
  await page.goto("/problems/mux4");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Мультиплексор 4:1");

  await test.step("the page has the card of the link with the OG picture", async () => {
    expect(await expectLinkCard(page, request)).toBe("Мультиплексор 4:1");
  });

  await test.step("the dialog gives the link of the problem", async () => {
    await page.getByRole("button", { name: "Поделиться задачей" }).click();
    const dialog = page.getByRole("dialog", { name: "Поделиться задачей" });
    await expect(dialog.getByTestId("share-preview")).toContainText("Мультиплексор 4:1");
    const url = await expectShareDialog(page, dialog);
    expect(new URL(url).pathname).toBe("/problems/mux4");
    await expectAccessible(page);
  });
});
