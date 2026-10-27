import { expect, it } from "vitest";

import type { History } from "@/features/guest/history";
import { problems } from "@/mocks/fixtures";

import { catalogView, solvedByLevel, statusOf } from "./view";

const history: History = {
  mux4: { status: "solved", difficulty: "easy" },
  "carry-adder": { status: "solved", difficulty: "easy" },
  "sync-fifo": { status: "attempted", difficulty: "medium" },
  gone: { status: "solved", difficulty: "hard" },
};

it("takes the page of the server as it is", () => {
  const data = { problems: problems.slice(0, 2), total: 5, complete: false, perPage: 2 };
  const view = catalogView(data, { status: [], page: 1 }, null);
  expect(view).toEqual({ problems: problems.slice(0, 2), total: 5, pages: 3 });
});

it("filters every problem by the local statuses and pages them", () => {
  const data = { problems, total: 5, complete: true, perPage: 2 };
  expect(catalogView(data, { status: ["solved"], page: 1 }, null)).toBeNull();
  const notSolved = catalogView(data, { status: ["attempted", "not_started"], page: 2 }, history);
  expect(notSolved?.problems.map((problem) => problem.slug)).toEqual(["sync-fifo"]);
  expect(notSolved).toMatchObject({ total: 3, pages: 2 });
  expect(catalogView(data, { status: ["solved"], page: 1 }, {})).toEqual({
    problems: [],
    total: 0,
    pages: 0,
  });
});

it("counts the solved problems per level", () => {
  expect(statusOf(history, "seq-detector")).toBe("not_started");
  expect(statusOf(history, "sync-fifo")).toBe("attempted");
  expect(solvedByLevel(history)).toEqual({ easy: 2, hard: 1 });
});
