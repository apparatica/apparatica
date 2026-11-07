// The leaderboard page of a problem, read by the server from the API as the user of the request
// sees it: the own entry and the card «Ваше решение» need the session.
import type { Schemas } from "@/lib/api/client";
import { sessionApi } from "@/lib/api/server";

import { BOARD_PER_PAGE, type BoardQuery } from "./query";

export interface BoardData {
  board: Schemas["ProblemLeaderboard"];
  /** The query the board answers: a sort the API refused falls back to the order of places. */
  query: BoardQuery;
}

/** null when the problem is not published or has no leaderboard: the page is a 404. */
export async function loadBoard(
  slug: string,
  query: BoardQuery,
  session: string | null,
): Promise<BoardData | null> {
  const get = (q: BoardQuery) =>
    sessionApi(session).GET("/api/v1/problems/{slug}/leaderboard", {
      params: {
        path: { slug },
        query: {
          page: q.page,
          per_page: BOARD_PER_PAGE,
          sort: q.sort,
          group: q.group,
          around: q.around ? "me" : null,
        },
      },
    });
  let result = await get(query);
  // A metric that is no column of this problem (an old link, a hand-edited address).
  if (result.response.status === 422 && query.sort !== "rank") {
    query = { ...query, sort: "rank" };
    result = await get(query);
  }
  if (result.response.status === 404) return null;
  if (result.data === undefined) {
    throw new Error(
      `GET /problems/${slug}/leaderboard: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return { board: result.data, query };
}
