// The data of a problem page, read by the server from the API. The page, its metadata and the
// breadcrumbs and status bar slots of the layout ask for it in one request: `cache` reads it once.
import { cache } from "react";

import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi, sessionApi } from "@/lib/api/server";

import type { AccountDrafts } from "./server-draft";

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

/** The draft of the user of the request (`session` is the session cookie); null for a guest or an
 * ended session. Any other failure leaves the page to the local draft, as for a guest. */
export async function loadServerDraft(
  slug: string,
  session: string | null,
): Promise<AccountDrafts | null> {
  if (session === null) return null;
  const { data, response } = await sessionApi(session).GET("/api/v1/me/drafts/{slug}", {
    params: { path: { slug } },
  });
  if (data !== undefined) return { draft: data };
  return response.status === 404 ? { draft: null } : null;
}
