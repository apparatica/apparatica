// The problem catalogue of the mock API: the demo problems, filtered and sorted like GET /problems
// does it (a search in the title and the tags, levels, tags, sorts, pages), and the tags.
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api } from "./http";

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
];
