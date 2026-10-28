// The data of a problem page, read by the server from the API. The page, its metadata and the
// breadcrumbs and status bar slots of the layout ask for it in one request: `cache` reads it once.
import { cache } from "react";

import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi } from "@/lib/api/server";

export interface ProblemData {
  problem: Schemas["ProblemDetail"];
  levels: Schemas["Difficulty"][];
  tags: Schemas["Tag"][];
}

function data<T>(result: { data?: T; error?: ApiError }, what: string): T {
  if (result.data === undefined) {
    throw new Error(
      `${what}: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return result.data;
}

/** null for a problem that is not published (or a slug the API rejects): the page is a 404. */
export const loadProblem = cache(async (slug: string): Promise<ProblemData | null> => {
  const [found, config, tags] = await Promise.all([
    serverApi.GET("/api/v1/problems/{slug}", { params: { path: { slug } } }),
    serverApi.GET("/api/v1/config").then((result) => data(result, "GET /config")),
    serverApi.GET("/api/v1/tags").then((result) => data(result, "GET /tags")),
  ]);
  if (found.error?.code === "NOT_FOUND" || found.error?.code === "VALIDATION_ERROR") return null;
  return {
    problem: data(found, `GET /problems/${slug}`),
    levels: config.difficulties,
    tags,
  };
});
