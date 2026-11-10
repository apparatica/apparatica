import { screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { config } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";

import { fillIn, LEGAL_DOCUMENTS, legalText } from "./documents";
import { LegalIndex, LegalPage } from "./legal-page";

const OPERATOR = { name: "Ада Лавлейс", email: "privacy@example.com" };
// Pages of the site the texts may link to.
const ROUTES = new Set(["/settings", "/legal", ...LEGAL_DOCUMENTS.map((key) => `/legal/${key}`)]);

it("fills in the operator and refuses an unknown placeholder", () => {
  expect(fillIn("{{operator.name}}, {{operator.email}}", OPERATOR)).toBe(
    "Ада Лавлейс, privacy@example.com",
  );
  expect(() => fillIn("{{operator.phone}}", OPERATOR)).toThrow("{{operator.phone}}");
  expect(() => fillIn("{{operator.constructor}}", OPERATOR)).toThrow();
});

it.each(LEGAL_DOCUMENTS)("renders %s with the operator and links within the site", async (key) => {
  const text = await legalText(key, OPERATOR);
  expect(text).not.toMatch(/\{\{|\}\}/);
  for (const [, href] of text.matchAll(/\]\((\/[^)\s]*)\)/g)) {
    expect(ROUTES, `${key}: ${href}`).toContain(href);
  }
  renderWithProviders(<LegalPage document={key} markdown={text} version={null} draft={false} />);
  expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  expect(screen.queryByText(/^Редакция от/)).toBeNull();
  expect(screen.queryByRole("note")).toBeNull();
});

it("shows the edition and marks a draft", async () => {
  renderWithProviders(
    <LegalPage
      document="privacy"
      markdown={await legalText("privacy", config.legal.operator)}
      version="2026-11-03"
      draft
    />,
  );
  expect(
    screen.getByRole("heading", { level: 1, name: "Политика обработки персональных данных" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Редакция от 3 ноября 2026 г.")).toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent("Черновик");
  expect(screen.getByRole("link", { name: "Cookie" })).toHaveAttribute("href", "/legal/cookies");
  expect(screen.getAllByText(/contact@apparatica\.app/).length).toBeGreaterThan(0);
});

it("lists the documents", () => {
  renderWithProviders(<LegalIndex />);
  const links = within(screen.getByRole("list")).getAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/legal/terms",
    "/legal/privacy",
    "/legal/cookies",
  ]);
  expect(links[0]).toHaveTextContent("Пользовательское соглашение");
});
