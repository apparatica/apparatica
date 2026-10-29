// The accessibility check of the e2e tests (specs/09 §4.4): axe with the WCAG 2.2 A and AA rules on
// the page as a user sees it, no serious or critical violations (NFR-A11Y-06).
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const IMPACTS = new Set(["serious", "critical"]);

export async function expectAccessible(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(TAGS)
    // The waveview frame has an opaque origin (ADR-0004): axe cannot reach into it.
    .exclude('iframe[sandbox="allow-scripts"]')
    .analyze();
  const found = violations
    .filter(({ impact }) => IMPACTS.has(impact ?? ""))
    .map(({ id, help, nodes }) => ({
      rule: `${id}: ${help}`,
      nodes: nodes.map((node) => node.target.join(" ")),
    }));
  expect(found).toEqual([]);
}
