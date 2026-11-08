// «Поделиться» and the link cards in the e2e tests (FR-SHR-01..03).
import type { APIRequestContext, Locator, Page } from "@playwright/test";

import { expect } from "./fixtures";

/** The OG picture: 1200 × 630 PNG (web/src/features/share/og-image.tsx). */
const OG = { width: 1200, height: 630 };

const meta = (page: Page, property: string) =>
  page.locator(`meta[property="${property}"]`).getAttribute("content");

/** The width and height of a PNG from its IHDR chunk, right after the signature. */
function pngSize(body: Buffer) {
  expect(body.subarray(0, 8)).toEqual(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  );
  expect(body.subarray(12, 16).toString("ascii")).toBe("IHDR");
  return { width: body.readUInt32BE(16), height: body.readUInt32BE(20) };
}

/** The link card of the open page: its title and description, and its picture, which is an
 * absolute address on the site (a messenger fetches it without the page) and a PNG of the size
 * the meta tags declare. The title of the card. */
export async function expectLinkCard(page: Page, request: APIRequestContext): Promise<string> {
  const title = await meta(page, "og:title");
  expect(title, "og:title").toBeTruthy();
  expect(await meta(page, "og:description"), "og:description").toBeTruthy();
  const image = await meta(page, "og:image");
  expect(image, "og:image").toBeTruthy();
  expect(new URL(image!).origin, "the site of og:image").toBe(new URL(page.url()).origin);
  expect(await meta(page, "og:image:width")).toBe(String(OG.width));
  expect(await meta(page, "og:image:height")).toBe(String(OG.height));

  const response = await request.get(image!);
  expect(response.status(), `GET ${image}`).toBe(200);
  expect(response.headers()["content-type"]).toBe("image/png");
  expect(pngSize(await response.body())).toEqual(OG);
  return title!;
}

/** The open dialog «Поделиться …»: the link it gives, copied with «Копировать», and the same link
 * in the posts of VK, Telegram and X. The browser context needs the clipboard permissions. */
export async function expectShareDialog(page: Page, dialog: Locator): Promise<string> {
  const url = await dialog.getByRole("textbox", { name: /^Ссылка на/ }).inputValue();
  expect(new URL(url).origin, "the site of the link").toBe(new URL(page.url()).origin);

  await dialog.getByRole("button", { name: "Копировать" }).click();
  await expect(page.getByText("Ссылка скопирована")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(url);

  const networks: [name: string, host: string][] = [
    ["ВКонтакте", "vk.com"],
    ["Telegram", "t.me"],
    ["Пост в X", "x.com"],
  ];
  for (const [name, host] of networks) {
    const href = await dialog.getByRole("link", { name }).getAttribute("href");
    const post = new URL(href!);
    expect(post.host).toBe(host);
    expect(post.searchParams.get("url")).toBe(url);
  }
  return url;
}
