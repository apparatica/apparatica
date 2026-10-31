// The test of the e2e suite: every page it opens must keep to the Content Security Policy of the
// site (NFR-SEC-07). The browser reports a violation, blocked or not, in the console of the page,
// its frames included; any such report fails the test.
import { expect, test as base } from "@playwright/test";

export const test = base.extend<{ cspViolations: void }>({
  cspViolations: [
    async ({ page }, use) => {
      const violations: string[] = [];
      page.on("console", (message) => {
        if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
      });
      await use();
      expect(violations, "violations of the Content Security Policy").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
