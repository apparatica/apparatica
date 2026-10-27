// The problem catalogue of the mock API: the demo problems, filtered like GET /problems does it
// (a search in the title and the tag slugs, levels, tags, pages).
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api } from "./http";

export const problemHandlers = [
  http.get(api("/api/v1/problems"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    const q = params.get("q")?.trim().toLowerCase() ?? "";
    const levels = params.getAll("difficulty");
    const tags = params.getAll("tag");
    const page = Number(params.get("page") ?? 1);
    const perPage = Number(params.get("per_page") ?? 12);
    const found = fixtures.problems.filter(
      (problem) =>
        (q === "" ||
          problem.title.toLowerCase().includes(q) ||
          problem.tags.some((tag) => tag.includes(q))) &&
        (levels.length === 0 || levels.includes(problem.difficulty)) &&
        (tags.length === 0 || problem.tags.some((tag) => tags.includes(tag))),
    );
    const body: Schemas["ProblemPage"] = {
      items: found.slice((page - 1) * perPage, page * perPage),
      page,
      per_page: perPage,
      total: found.length,
      progress: fixtures.config.difficulties.map(({ key }) => ({
        difficulty: key,
        total: fixtures.problems.filter((problem) => problem.difficulty === key).length,
      })),
    };
    return HttpResponse.json(body);
  }),
];
