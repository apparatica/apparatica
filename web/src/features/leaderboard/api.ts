// Requests of the leaderboards (phase 3): the leaderboard of a problem.
import { browserApi as api } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";

export const leaderboardKeys = {
  all: ["leaderboards"] as const,
  problem: (problem: string) => ["leaderboards", "problem", problem] as const,
  /** The first place and the reference of a problem, without the rows. */
  top: (problem: string) => ["leaderboards", "problem", problem, "top"] as const,
};

/** The leaderboard of a problem with a single row: what is compared with is in any page. */
export async function getLeaderboardTop(problem: string): Promise<Schemas["ProblemLeaderboard"]> {
  const { data, error } = await api.GET("/api/v1/problems/{slug}/leaderboard", {
    params: { path: { slug: problem }, query: { per_page: 1 } },
  });
  if (error !== undefined) throw error;
  return data;
}
