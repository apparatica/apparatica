// The state of the catalogue in its address (FR-CAT-02): search, filters, sort and page. The
// page is rendered from it on the server, the controls change it.
import type { paths } from "@/lib/api/client";

export type Sort = NonNullable<
  NonNullable<paths["/api/v1/problems"]["get"]["parameters"]["query"]>["sort"]
>;

/** In the order of the sort menu. */
export const SORTS = [
  "number",
  "-number",
  "difficulty",
  "-difficulty",
  "-acceptance",
  "acceptance",
] as const satisfies readonly Sort[];

/** Statuses of the local history; "not started" is a problem without one. */
export const STATUSES = ["solved", "attempted", "not_started"] as const;
export type StatusFilter = (typeof STATUSES)[number];

export interface CatalogQuery {
  q: string;
  difficulty: string[];
  tag: string[];
  status: StatusFilter[];
  sort: Sort;
  page: number;
}

/** The search parameters of a page, as Next.js passes them. */
export type SearchParams = Record<string, string | string[] | undefined>;

const MAX_QUERY = 100; // the limit of the API

const values = (value: string | string[] | undefined): string[] =>
  value === undefined ? [] : [...new Set(Array.isArray(value) ? value : [value])];

const isOneOf = <T extends string>(options: readonly T[], value: string | undefined): value is T =>
  options.includes(value as T);

/** Unknown or broken values are dropped: a hand-edited address still opens the catalogue. */
export function parseCatalogQuery(params: SearchParams): CatalogQuery {
  const [sort] = values(params.sort);
  const page = Number(values(params.page)[0]);
  return {
    q: (values(params.q)[0] ?? "").slice(0, MAX_QUERY),
    difficulty: values(params.difficulty),
    tag: values(params.tag),
    status: values(params.status).filter((status) => isOneOf(STATUSES, status)),
    sort: isOneOf(SORTS, sort) ? sort : "number",
    page: Number.isSafeInteger(page) && page >= 1 ? page : 1,
  };
}

/** The address of the catalogue; defaults are left out. */
export function catalogHref(query: CatalogQuery): string {
  const params = new URLSearchParams();
  if (query.q.trim() !== "") params.set("q", query.q);
  for (const level of query.difficulty) params.append("difficulty", level);
  for (const tag of query.tag) params.append("tag", tag);
  for (const status of query.status) params.append("status", status);
  if (query.sort !== "number") params.set("sort", query.sort);
  if (query.page > 1) params.set("page", String(query.page));
  const search = params.toString();
  return search === "" ? "/problems" : `/problems?${search}`;
}

export function hasFilters(query: CatalogQuery): boolean {
  return (
    query.q.trim() !== "" ||
    query.difficulty.length > 0 ||
    query.tag.length > 0 ||
    query.status.length > 0
  );
}

/** Without the search and the filters, on the first page; the sort stays. */
export const withoutFilters = (query: CatalogQuery): CatalogQuery => ({
  q: "",
  difficulty: [],
  tag: [],
  status: [],
  sort: query.sort,
  page: 1,
});
