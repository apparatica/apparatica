import { expect, it } from "vitest";

import { catalogHref, hasFilters, parseCatalogQuery, withoutFilters } from "./query";

it("reads the defaults from an empty address", () => {
  const query = parseCatalogQuery({});
  expect(query).toEqual({ q: "", difficulty: [], tag: [], status: [], sort: "number", page: 1 });
  expect(catalogHref(query)).toBe("/problems");
  expect(hasFilters(query)).toBe(false);
});

it("keeps the filters through the address", () => {
  const query = parseCatalogQuery({
    q: "fifo",
    difficulty: ["medium", "hard"],
    tag: "fifo",
    status: ["solved", "not_started"],
    sort: "-acceptance",
    page: "2",
  });
  expect(query).toEqual({
    q: "fifo",
    difficulty: ["medium", "hard"],
    tag: ["fifo"],
    status: ["solved", "not_started"],
    sort: "-acceptance",
    page: 2,
  });
  const href = catalogHref(query);
  expect(href).toBe(
    "/problems?q=fifo&difficulty=medium&difficulty=hard&tag=fifo&status=solved&status=not_started&sort=-acceptance&page=2",
  );
  const params = new URLSearchParams(href.split("?")[1]);
  const again: Record<string, string[]> = {};
  for (const [key, value] of params) again[key] = [...(again[key] ?? []), value];
  expect(parseCatalogQuery(again)).toEqual(query);
});

it("drops what it does not know", () => {
  expect(
    parseCatalogQuery({
      q: ["a", "b"],
      difficulty: ["easy", "easy"],
      status: ["solved", "won"],
      sort: "status",
      page: "-1",
    }),
  ).toEqual({ q: "a", difficulty: ["easy"], tag: [], status: ["solved"], sort: "number", page: 1 });
  expect(parseCatalogQuery({ page: "1.5" }).page).toBe(1);
  expect(parseCatalogQuery({ q: "x".repeat(150) }).q).toHaveLength(100);
  expect(catalogHref(parseCatalogQuery({ q: "  " }))).toBe("/problems");
});

it("resets the filters but keeps the sort", () => {
  const query = parseCatalogQuery({ q: "x", tag: "fsm", sort: "difficulty", page: "3" });
  expect(hasFilters(query)).toBe(true);
  expect(catalogHref(withoutFilters(query))).toBe("/problems?sort=difficulty");
});
