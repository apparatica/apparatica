// Requests of the leaderboards (phase 3) from the browser: the leaderboard of a problem and its
// public solutions. Every key of a problem starts with `problem(slug)`: an accepted Submit
// resets them all.
import { browserApi as api } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";

export const leaderboardKeys = {
  all: ["leaderboards"] as const,
  problem: (problem: string) => ["leaderboards", "problem", problem] as const,
  /** The first place and the reference of a problem, without the rows. */
  top: (problem: string) => ["leaderboards", "problem", problem, "top"] as const,
  /** The short leaderboard of the tab «Рейтинг». */
  short: (problem: string) => ["leaderboards", "problem", problem, "short"] as const,
  /** Public solutions of the tab «Решения» in an order. */
  solutions: (problem: string, sort: string) =>
    ["leaderboards", "problem", problem, "solutions", sort] as const,
};

export interface BoardRequest {
  page?: number;
  per_page?: number;
  sort?: string;
  group?: boolean;
  around?: "me" | null;
}

/** A page of the leaderboard of a problem. */
export async function getLeaderboard(
  problem: string,
  query: BoardRequest = {},
): Promise<Schemas["ProblemLeaderboard"]> {
  const { data, error } = await api.GET("/api/v1/problems/{slug}/leaderboard", {
    params: { path: { slug: problem }, query },
  });
  if (error !== undefined) throw error;
  return data;
}

/** The leaderboard of a problem with a single row: what is compared with is in any page. */
export const getLeaderboardTop = (problem: string) => getLeaderboard(problem, { per_page: 1 });

/** A page of the public solutions of a problem, of every version. */
export async function getSolutions(
  problem: string,
  query: { sort: string; page: number; per_page: number },
): Promise<Schemas["SolutionPage"]> {
  const { data, error } = await api.GET("/api/v1/problems/{slug}/solutions", {
    params: { path: { slug: problem }, query },
  });
  if (error !== undefined) throw error;
  return data;
}
