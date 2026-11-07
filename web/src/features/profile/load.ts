// The data of a profile page, read by the server from the API. The page, its metadata and the
// breadcrumbs slot of the layout ask for it in one request: `cache` reads it once.
import { cache } from "react";

import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi } from "@/lib/api/server";

/** Public solutions listed in the profile before «Все N». */
export const SOLUTIONS_SHOWN = 5;
/** Public solutions on a page of the list. */
export const SOLUTIONS_PER_PAGE = 20;

export interface ProfileData {
  profile: Schemas["Profile"];
  levels: Schemas["Difficulty"][];
  /** The newest public solutions, up to SOLUTIONS_SHOWN. */
  solutions: Schemas["SolutionSummary"][];
}

export interface UserSolutionsData {
  nick: string;
  solutions: Schemas["UserSolutionPage"];
}

function data<T>(result: { data?: T; error?: ApiError }, what: string): T {
  if (result.data === undefined) {
    throw new Error(
      `${what}: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return result.data;
}

/** null when nobody has the nick (or the API rejects it): the page is a 404. */
const missing = (error: ApiError | undefined) =>
  error?.code === "NOT_FOUND" || error?.code === "VALIDATION_ERROR";

const solutionsOf = (nick: string, page: number, perPage: number) =>
  serverApi.GET("/api/v1/users/{nick}/solutions", {
    params: { path: { nick }, query: { page, per_page: perPage } },
  });

const levelsOf = () =>
  serverApi.GET("/api/v1/config").then((result) => data(result, "GET /config").difficulties);

/** null for a nick nobody has (or one the API rejects): the page is a 404. */
export const loadProfile = cache(async (nick: string): Promise<ProfileData | null> => {
  const [found, solutions, levels] = await Promise.all([
    serverApi.GET("/api/v1/users/{nick}", { params: { path: { nick } } }),
    solutionsOf(nick, 1, SOLUTIONS_SHOWN),
    levelsOf(),
  ]);
  if (missing(found.error) || missing(solutions.error)) return null;
  return {
    profile: data(found, `GET /users/${nick}`),
    levels,
    solutions: data(solutions, `GET /users/${nick}/solutions`).items,
  };
});

/** A page of the public solutions of a nick; null: nobody has the nick. */
export const loadUserSolutions = cache(
  async (nick: string, page: number): Promise<UserSolutionsData | null> => {
    const found = await solutionsOf(nick, page, SOLUTIONS_PER_PAGE);
    if (missing(found.error)) return null;
    return { nick, solutions: data(found, `GET /users/${nick}/solutions`) };
  },
);
