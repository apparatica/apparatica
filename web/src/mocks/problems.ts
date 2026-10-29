// The problem catalogue of the mock API: the demo problems, filtered and sorted like GET /problems
// does it (a search in the title and the tags, levels, tags, sorts, pages), the tags and the pages
// of the problems: their current versions from problems/ (scripts/mock_problems.py).
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api, problem as apiProblem } from "./http";
import versions from "./problem-versions.json";

/** A backend test validates the file against the API schema, which makes the cast safe. */
const details = versions as Schemas["ProblemVersionDetail"][];

function findVersion(slug: string): Schemas["ProblemVersionDetail"] | undefined {
  return details.find((detail) => detail.slug === slug);
}

type Problem = Schemas["ProblemListItem"];

const levels = fixtures.config.difficulties.map(({ key }) => key);
const byNumber = (problem: Problem) => problem.number;
const SORT_KEYS: Record<string, (problem: Problem) => number | null> = {
  number: byNumber,
  difficulty: (problem) => levels.indexOf(problem.difficulty),
  acceptance: (problem) => problem.acceptance,
};

/** Without a value last in both directions, then by number. */
function compare(sort: string): (a: Problem, b: Problem) => number {
  const key = SORT_KEYS[sort.replace(/^-/, "")] ?? byNumber;
  const direction = sort.startsWith("-") ? -1 : 1;
  return (a, b) => {
    const [x, y] = [key(a), key(b)];
    if (x !== y) {
      if (x === null) return 1;
      if (y === null) return -1;
      return (x - y) * direction;
    }
    return a.number - b.number;
  };
}

function matches(problem: Problem, q: string): boolean {
  const titles = problem.tags.map(
    (slug) => fixtures.tags.find((tag) => tag.slug === slug)?.title ?? slug,
  );
  return [problem.title, ...problem.tags, ...titles].some((text) => text.toLowerCase().includes(q));
}

export const problemHandlers = [
  http.get(api("/api/v1/tags"), () => HttpResponse.json(fixtures.tags)),
  http.get(api("/api/v1/problems"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    const q = params.get("q")?.trim().toLowerCase() ?? "";
    const difficulties = params.getAll("difficulty");
    const tags = params.getAll("tag");
    const page = Number(params.get("page") ?? 1);
    const perPage = Number(params.get("per_page") ?? fixtures.config.catalog.per_page);
    const found = fixtures.problems
      .filter(
        (problem) =>
          (q === "" || matches(problem, q)) &&
          (difficulties.length === 0 || difficulties.includes(problem.difficulty)) &&
          (tags.length === 0 || problem.tags.some((tag) => tags.includes(tag))),
      )
      .sort(compare(params.get("sort") ?? "number"));
    const body: Schemas["ProblemPage"] = {
      items: found.slice((page - 1) * perPage, page * perPage),
      page,
      per_page: perPage,
      total: found.length,
      progress: levels.map((key) => ({
        difficulty: key,
        total: fixtures.problems.filter((problem) => problem.difficulty === key).length,
      })),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/problems/:slug"), ({ params }) => {
    const slug = String(params.slug);
    const found = findVersion(slug);
    if (found === undefined) return apiProblem(404, "NOT_FOUND", `No published problem '${slug}'`);
    const acceptance = fixtures.problems.find((item) => item.slug === slug)?.acceptance ?? null;
    const body: Schemas["ProblemDetail"] = { ...found, acceptance };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/problems/:slug/versions/:version"), ({ params }) => {
    const slug = String(params.slug);
    const found = findVersion(slug);
    if (found === undefined || String(found.version) !== params.version) {
      return apiProblem(404, "NOT_FOUND", `No published version ${String(params.version)}`);
    }
    return HttpResponse.json(found);
  }),
  // The demo problems have no pictures in their statements.
  http.get(api("/api/v1/problems/:slug/versions/:version/assets/*"), ({ params }) =>
    apiProblem(404, "NOT_FOUND", `No picture in version ${String(params.version)}`),
  ),
];
