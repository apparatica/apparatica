import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";

import { loadCatalog } from "./load";
import { parseCatalogQuery } from "./query";

it("reads a page of the query, the levels and the tags", async () => {
  const data = await loadCatalog(parseCatalogQuery({ difficulty: "easy", sort: "-acceptance" }));
  expect(data.problems.map((problem) => problem.slug)).toEqual([
    "mux4",
    "counter-mod-n",
    "carry-adder",
  ]);
  expect(data).toMatchObject({
    levels: config.difficulties,
    tags,
    perPage: 12,
    total: 3,
    complete: false,
  });
  expect(data.progress).toEqual([
    { difficulty: "easy", total: 3 },
    { difficulty: "medium", total: 2 },
    { difficulty: "hard", total: 0 },
  ]);
});

it("reads every problem of the other filters when the status filter is on", async () => {
  const many = Array.from({ length: 230 }, (_, index) => ({
    slug: `p${index}`,
    number: index + 1,
    title: `Задача ${index + 1}`,
    difficulty: "easy",
    tags: [],
    acceptance: null,
  }));
  const requests: URLSearchParams[] = [];
  server.use(
    http.get(api("/api/v1/problems"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      const page = Number(params.get("page"));
      const perPage = Number(params.get("per_page"));
      const body: Schemas["ProblemPage"] = {
        items: many.slice((page - 1) * perPage, page * perPage),
        page,
        per_page: perPage,
        total: many.length,
        progress: [],
      };
      return HttpResponse.json(body);
    }),
  );
  const data = await loadCatalog(parseCatalogQuery({ q: "x", status: "solved", page: "4" }));
  expect(data.complete).toBe(true);
  expect(data.problems.map((problem) => problem.number)).toEqual(many.map((p) => p.number));
  expect(requests.map((params) => params.get("page"))).toEqual(["1", "2", "3"]);
  expect(requests.every((params) => params.get("per_page") === "100")).toBe(true);
  expect(requests.every((params) => params.get("q") === "x" && !params.has("status"))).toBe(true);
});

it("fails when the API does", async () => {
  server.use(http.get(api("/api/v1/tags"), () => HttpResponse.json({}, { status: 503 })));
  await expect(loadCatalog(parseCatalogQuery({}))).rejects.toThrow(/GET \/tags/);
});
