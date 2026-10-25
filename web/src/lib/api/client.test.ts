import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { config } from "@/mocks/fixtures";
import { api } from "@/mocks/handlers";
import { server } from "@/mocks/server";

import { createApiClient } from "./client";

const client = createApiClient({ baseUrl: "http://localhost" });

it("returns typed data from the API", async () => {
  const { data, error } = await client.GET("/api/v1/config");
  expect(error).toBeUndefined();
  expect(data?.difficulties.map((level) => level.key)).toEqual(["easy", "medium", "hard"]);
  expect(data).toEqual(config);
});

it("returns problem+json errors as typed errors", async () => {
  server.use(
    http.get(api("/api/v1/problems/:slug"), () =>
      HttpResponse.json(
        {
          type: "https://apparatica.app/errors/not-found",
          title: "Not Found",
          status: 404,
          code: "NOT_FOUND",
        },
        { status: 404, headers: { "Content-Type": "application/problem+json" } },
      ),
    ),
  );
  const { data, error, response } = await client.GET("/api/v1/problems/{slug}", {
    params: { path: { slug: "no-such-problem" } },
  });
  expect(data).toBeUndefined();
  expect(response.status).toBe(404);
  expect(error?.code).toBe("NOT_FOUND");
});
