// The data of the catalogue page, read by the server from the API. For a signed-in user the API
// gives the statuses of the user and filters by them (FR-CAT-03); a guest's statuses live in the
// browser, which filters and pages them itself.
import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi, sessionApi } from "@/lib/api/server";

import type { CatalogQuery } from "./query";

const MAX_PER_PAGE = 100; // the limit of the API

export interface CatalogData {
  levels: Schemas["Difficulty"][];
  tags: Schemas["Tag"][];
  perPage: number;
  /** Problems of every level, whatever the filters. */
  progress: Schemas["DifficultyTotal"][];
  /** The page of the query; for a guest with the status filter, every problem that matches the
   * other filters (`complete`): the statuses live in the browser, which filters and pages them. */
  problems: Schemas["ProblemListItem"][];
  /** Problems that match the filters of the API. */
  total: number;
  complete: boolean;
  /** The problems and the progress carry the statuses of the signed-in user. */
  own: boolean;
}

function data<T>(result: { data?: T; error?: ApiError }, what: string): T {
  if (result.data === undefined) {
    throw new Error(
      `${what}: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return result.data;
}

/** `session`: the session cookie of the request, if any. */
export async function loadCatalog(
  query: CatalogQuery,
  session: string | null = null,
): Promise<CatalogData> {
  const filters = {
    q: query.q.trim() === "" ? null : query.q,
    difficulty: query.difficulty,
    tag: query.tag,
    sort: query.sort,
  };
  const getPage = async (page: number, perPage: number | null = null) =>
    data(
      await serverApi.GET("/api/v1/problems", {
        params: { query: { ...filters, page, per_page: perPage } },
      }),
      "GET /problems",
    );
  // The user's page; null when the session has ended: then it is a guest's.
  const getOwnPage = async () => {
    const result = await sessionApi(session).GET("/api/v1/problems", {
      params: { query: { ...filters, status: query.status, page: query.page } },
    });
    if (result.response.status === 401) return null;
    const page = data(result, "GET /problems");
    return page.progress.every((level) => level.solved !== null) ? page : null;
  };

  const getGuestPage = () =>
    query.status.length > 0 ? getPage(1, MAX_PER_PAGE) : getPage(query.page);

  const [config, tags, own, guest] = await Promise.all([
    serverApi.GET("/api/v1/config").then((result) => data(result, "GET /config")),
    serverApi.GET("/api/v1/tags").then((result) => data(result, "GET /tags")),
    session === null ? null : getOwnPage(),
    session === null ? getGuestPage() : null,
  ]);
  const first = own ?? guest ?? (await getGuestPage());
  const complete = own === null && query.status.length > 0;
  const problems = [...first.items];
  if (complete) {
    const pages = Math.ceil(first.total / MAX_PER_PAGE);
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, index) => getPage(index + 2, MAX_PER_PAGE)),
    );
    for (const page of rest) problems.push(...page.items);
  }
  return {
    levels: config.difficulties,
    tags,
    perPage: config.catalog.per_page,
    progress: first.progress,
    problems,
    total: first.total,
    complete,
    own: own !== null,
  };
}
