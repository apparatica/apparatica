import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { config, tags } from "@/mocks/fixtures";
import { api, problem as apiProblem } from "@/mocks/http";
import { server } from "@/mocks/server";

import { loadProblem } from "./load";

it("reads the current version with its acceptance rate, the levels and the tags", async () => {
  const data = await loadProblem("mux4");
  expect(data?.problem).toMatchObject({
    slug: "mux4",
    title: "Мультиплексор 4:1",
    acceptance: 0.78,
    language: "systemverilog",
  });
  expect(data?.levels).toEqual(config.difficulties);
  expect(data?.tags).toEqual(tags);
});

it("is null for a problem that is not published or a slug the API rejects", async () => {
  expect(await loadProblem("no-such-problem")).toBeNull();
  server.use(
    http.get(api("/api/v1/problems/:slug"), () =>
      apiProblem(422, "VALIDATION_ERROR", "Invalid slug"),
    ),
  );
  expect(await loadProblem("Bad_Slug")).toBeNull();
});

it("fails on other errors of the API", async () => {
  server.use(
    http.get(api("/api/v1/problems/:slug"), () => HttpResponse.json(null, { status: 503 })),
  );
  await expect(loadProblem("mux4")).rejects.toThrow("GET /problems/mux4");
});
