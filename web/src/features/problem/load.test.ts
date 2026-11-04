import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { config, tags } from "@/mocks/fixtures";
import { api, problem as apiProblem } from "@/mocks/http";
import { server } from "@/mocks/server";
import { mockSession } from "@/mocks/users";

import { loadProblem, loadServerDraft } from "./load";

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

it("reads the draft of the signed-in user of the request", async () => {
  expect(await loadServerDraft("mux4", null)).toBeNull(); // a guest
  const session = mockSession("ada");
  expect(await loadServerDraft("mux4", session)).toEqual({ draft: null });
  await fetch("http://localhost:8000/api/v1/me/drafts/mux4", {
    method: "PUT",
    headers: { Cookie: `ap_session=${session}`, "Content-Type": "application/json" },
    body: JSON.stringify({ code: "module mux4; endmodule", problem_version: 1 }),
  });
  expect(await loadServerDraft("mux4", session)).toMatchObject({
    draft: { code: "module mux4; endmodule", problem_version: 1 },
  });
  expect(await loadServerDraft("mux4", "mock.ended")).toBeNull(); // as a guest
  server.use(
    http.get(api("/api/v1/me/drafts/:slug"), () => HttpResponse.json({}, { status: 503 })),
  );
  expect(await loadServerDraft("mux4", session)).toBeNull(); // the local draft will do
});
