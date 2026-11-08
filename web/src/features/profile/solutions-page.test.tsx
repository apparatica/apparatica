import { screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { renderWithProviders } from "@/test/render";

import { UserSolutionsPage } from "./solutions-page";

function item(index: number): Schemas["SolutionSummary"] {
  return {
    id: `solution-${index}`,
    problem: { slug: "mux4", number: 1, title: "Мультиплексор 4:1", difficulty: "easy" },
    version: 1,
    author: { nick: "ada", display_name: null, avatar_url: null, deleted: false },
    status: "accepted",
    metrics: { "synth.critical_path_ns": 0.19 },
    rank: index === 21 ? 3 : null,
    duplicate_of: null,
    submitted_at: "2026-10-04T12:00:00Z",
  };
}

it("shows a page of the solutions with the pages around it", () => {
  renderWithProviders(
    <UserSolutionsPage
      nick="ada"
      solutions={{ items: [item(21), item(22)], page: 2, per_page: 20, total: 22 }}
    />,
  );
  expect(screen.getByRole("heading", { level: 1, name: "Решения ada" })).toBeInTheDocument();
  expect(screen.getByText(/22 публичных решения/)).toBeInTheDocument();
  const list = screen.getByRole("region", { name: "Публичные решения ada" });
  expect(within(list).getAllByRole("link")).toHaveLength(2);
  expect(within(list).getAllByRole("link")[0]).toHaveTextContent("0,19 нс · место 3");
  expect(screen.getByText(/Решения/, { selector: "span" })).toHaveTextContent(
    "Решения 21–22 из 22",
  );
  expect(screen.getByRole("link", { name: "Страница 1" })).toHaveAttribute(
    "href",
    "/u/ada/solutions",
  );
  expect(screen.getByRole("link", { name: "К профилю" })).toHaveAttribute("href", "/u/ada");
});

it("tells when there are none", () => {
  renderWithProviders(
    <UserSolutionsPage nick="bob" solutions={{ items: [], page: 1, per_page: 20, total: 0 }} />,
  );
  expect(screen.getByRole("heading", { name: "Пока нет публичных решений" })).toBeInTheDocument();
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});
