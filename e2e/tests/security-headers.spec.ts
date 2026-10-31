// The headers of the pages (NFR-SEC-07, docs/security.md#csp-сайта): a Content Security Policy with
// a nonce of each response that the scripts of the page carry, no eval; the headers of Caddy.
import { expect, test } from "./fixtures";

test("a page has a policy with a nonce of its own", async ({ page, request }) => {
  const response = await page.goto("/problems/mux4");
  const headers = response!.headers();
  const policy = headers["content-security-policy"]!;
  const nonce = /'nonce-([^']+)'/.exec(policy)?.[1];
  expect(nonce).toBeDefined();
  expect(policy).toContain("'strict-dynamic'");
  expect(policy).not.toContain("'unsafe-eval'");
  expect(policy).toContain("frame-ancestors 'none'");

  // The browser hides the attribute from the markup; the property keeps it.
  const nonces = await page
    .locator("script")
    .evaluateAll((scripts) =>
      scripts
        .filter((script) => !script.textContent?.includes("prefers-color-scheme"))
        .map((script) => (script as HTMLScriptElement).nonce),
    );
  expect(nonces.length).toBeGreaterThan(0);
  expect(new Set(nonces)).toEqual(new Set([nonce]));

  const again = (await request.get("/problems/mux4")).headers()["content-security-policy"];
  expect(again).not.toContain(`'nonce-${nonce}'`);

  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
  expect(headers["permissions-policy"]).toContain("camera=()");
  expect(headers["server"]).toBeUndefined();
});

test("the pages of errors keep to the policy", async ({ page }) => {
  for (const path of ["/problems/no-such-problem", "/no/such/page"]) {
    const response = await page.goto(path);
    expect(response!.headers()["content-security-policy"]).toContain("'nonce-");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  }
});
