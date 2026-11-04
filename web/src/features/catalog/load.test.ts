import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";
import { mockSession } from "@/mocks/users";

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
    { difficulty: "easy", total: 3, solved: null },
    { difficulty: "medium", total: 2, solved: null },
    { difficulty: "hard", total: 0, solved: null },
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
    status: null,
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

it("reads the page of a signed-in user, filtered by the server", async () => {
  const requests: Request[] = [];
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname === "/api/v1/problems") requests.push(request.clone());
  });
  const data = await loadCatalog(
    parseCatalogQuery({ status: "solved", page: "1" }),
    mockSession("ada"),
  );
  server.events.removeAllListeners();
  expect(data).toMatchObject({ own: true, complete: false });
  expect(data.problems.map((problem) => [problem.slug, problem.status])).toEqual([
    ["mux4", "solved"],
    ["carry-adder", "solved"],
  ]);
  expect(data.progress.find((level) => level.difficulty === "easy")?.solved).toBe(2);
  expect(requests).toHaveLength(1);
  expect(requests[0]?.headers.get("cookie")).toBe(`ap_session=${mockSession("ada")}`);
  expect(new URL(requests[0]?.url ?? "").searchParams.getAll("status")).toEqual(["solved"]);
});

it("reads the page of a guest when the session has ended", async () => {
  const data = await loadCatalog(parseCatalogQuery({ status: "solved" }), "mock.ended");
  expect(data).toMatchObject({ own: false, complete: true });
  expect(data.problems.every((problem) => problem.status === null)).toBe(true);
});

it("fails when the API does", async () => {
  server.use(http.get(api("/api/v1/tags"), () => HttpResponse.json({}, { status: 503 })));
  await expect(loadCatalog(parseCatalogQuery({}))).rejects.toThrow(/GET \/tags/);
});
