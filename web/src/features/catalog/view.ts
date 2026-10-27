// What the catalogue shows: the problems of the page with the statuses of the local history.
import type { History } from "@/features/guest/history";
import type { Schemas } from "@/lib/api/client";

import type { CatalogData } from "./load";
import type { CatalogQuery, StatusFilter } from "./query";

export function statusOf(history: History, slug: string): StatusFilter {
  return history[slug]?.status ?? "not_started";
}

export interface CatalogView {
  problems: Schemas["ProblemListItem"][];
  /** Problems that match the query, the status filter included. */
  total: number;
  pages: number;
}

/** Null while the view needs the statuses and they are unknown: on the server and during
 * hydration, with the status filter on. */
export function catalogView(
  data: Pick<CatalogData, "problems" | "total" | "complete" | "perPage">,
  query: Pick<CatalogQuery, "status" | "page">,
  history: History | null,
): CatalogView | null {
  const pages = (total: number) => Math.ceil(total / data.perPage);
  if (!data.complete) {
    return { problems: data.problems, total: data.total, pages: pages(data.total) };
  }
  if (history === null) return null;
  const found = data.problems.filter((problem) =>
    query.status.includes(statusOf(history, problem.slug)),
  );
  const from = (query.page - 1) * data.perPage;
  return {
    problems: found.slice(from, from + data.perPage),
    total: found.length,
    pages: pages(found.length),
  };
}

/** Solved problems per level. */
export function solvedByLevel(history: History): Record<string, number> {
  const solved: Record<string, number> = {};
  for (const { status, difficulty } of Object.values(history)) {
    if (status === "solved") solved[difficulty] = (solved[difficulty] ?? 0) + 1;
  }
  return solved;
}
