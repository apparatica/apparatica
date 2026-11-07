// The global leaderboard, read by the server from the API as the user of the request sees it:
// the own row and the rows around it need the session.
import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi, sessionApi } from "@/lib/api/server";

import { RATING_PER_PAGE } from "./query";

export interface RatingData {
  rating: Schemas["GlobalLeaderboard"];
  levels: Schemas["Difficulty"][];
}

function data<T>(result: { data?: T; error?: ApiError }, what: string): T {
  if (result.data === undefined) {
    throw new Error(
      `${what}: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return result.data;
}

export async function loadRating(page: number, session: string | null): Promise<RatingData> {
  const [rating, config] = await Promise.all([
    sessionApi(session)
      .GET("/api/v1/leaderboard", { params: { query: { page, per_page: RATING_PER_PAGE } } })
      .then((result) => data(result, "GET /leaderboard")),
    serverApi.GET("/api/v1/config").then((result) => data(result, "GET /config")),
  ]);
  return { rating, levels: config.difficulties };
}
