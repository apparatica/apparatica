// The state of the leaderboard page of a problem in its address (specs/08 §1): page, sort,
// grouping of duplicates and «К моей строке». The server renders the page from it.
import type { Schemas } from "@/lib/api/client";

import { type Direction, directionOf } from "./metrics";

export interface BoardQuery {
  page: number;
  /** rank, ±submitted_at or ±a metric of the columns (the API checks the columns). */
  sort: string;
  /** Fold later solutions with the same syntax tree (FR-LB-04). */
  group: boolean;
  /** The page with the own entry instead of `page`. */
  around: boolean;
}

/** Rows of a page of the full leaderboard. */
export const BOARD_PER_PAGE = 20;

export const DEFAULT_QUERY: BoardQuery = { page: 1, sort: "rank", group: true, around: false };

const SORT = /^(rank|-?submitted_at|-?[a-z_]+\.[a-z0-9_]+)$/; // the pattern of the API

type SearchParams = Record<string, string | string[] | undefined>;
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/** Unknown or broken values are dropped: a hand-edited address still opens the page. */
export function parseBoardQuery(params: SearchParams): BoardQuery {
  const page = Number(first(params.page));
  const sort = first(params.sort) ?? "";
  return {
    page: Number.isSafeInteger(page) && page >= 1 ? page : 1,
    sort: SORT.test(sort) && sort.length <= 64 ? sort : "rank",
    group: first(params.group) !== "0",
    around: first(params.around) === "me",
  };
}

export const leaderboardPath = (slug: string) =>
  `/problems/${encodeURIComponent(slug)}/leaderboard`;

/** The address of the page; defaults are left out. */
export function leaderboardHref(slug: string, query: Partial<BoardQuery> = {}): string {
  const { page, sort, group, around } = { ...DEFAULT_QUERY, ...query };
  const params = new URLSearchParams();
  if (around) params.set("around", "me");
  else if (page > 1) params.set("page", String(page));
  if (sort !== "rank") params.set("sort", sort);
  if (!group) params.set("group", "0");
  const search = params.toString();
  return search === "" ? leaderboardPath(slug) : `${leaderboardPath(slug)}?${search}`;
}

export interface ColumnSort {
  /** The column orders the rows now… */
  active: boolean;
  /** …in this direction (of the values, not of the places). */
  dir: Direction;
  /** The sort a click on the header asks for. */
  next: string;
}

const reverse = (dir: Direction): Direction => (dir === "asc" ? "desc" : "asc");
const sortOf = (key: string, dir: Direction) => (dir === "asc" ? key : `-${key}`);

/** How a column of metrics (or `submitted_at`) sorts. The main metric stands for `rank`: the
 * order of the places goes in its direction, and the first click on another column sorts in the
 * direction where the better values come first; the dates start from the newest. */
export function columnSort(
  key: string,
  sort: string,
  order: readonly Schemas["LeaderboardKey"][],
): ColumnSort {
  const natural: Direction = key === "submitted_at" ? "desc" : directionOf(key, order);
  const primary = order[0]?.metric === key;
  const current = sort.replace(/^-/, "");
  if (primary && sort === "rank") {
    return { active: true, dir: natural, next: sortOf(key, reverse(natural)) };
  }
  if (current !== key) {
    return { active: false, dir: natural, next: primary ? "rank" : sortOf(key, natural) };
  }
  const dir: Direction = sort.startsWith("-") ? "desc" : "asc";
  const next =
    dir === natural ? sortOf(key, reverse(natural)) : primary ? "rank" : sortOf(key, natural);
  return { active: true, dir, next };
}
