import { describe, expect, it } from "vitest";

import type { Check, TestCase } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import versions from "@/mocks/problem-versions.json";
import { scenarios } from "@/mocks/scenarios";
import { eventsUntil, playCheck, queuedCheck } from "@/test/checks";

import { testsCount, testsView } from "./tests-view";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];

const rowsOf = (check: Check, problem = FIFO) => {
  const [section, ...rest] = testsView(check, problem);
  expect(rest).toEqual([]);
  return section?.rows ?? [];
};

const test = (id: string, status: TestCase["status"], extra: Partial<TestCase> = {}): TestCase => ({
  id,
  name: `name ${id}`,
  group: "public",
  status,
  duration_ms: null,
  cycle: null,
  mismatches: [],
  ...extra,
});

/** A finished check of the wrong-answer scenario with other tests of its simulation. */
function withTests(tests: TestCase[]): Check {
  const check = playCheck(scenarios["wrong-answer"]);
  return {
    ...check,
    stages: check.stages.map((stage) =>
      stage.key === "sim_run" ? { ...stage, summary: { ...stage.summary, tests } } : stage,
    ),
  };
}

describe("the open tests", () => {
  it("wait for the simulation in a queued check", () => {
    const rows = rowsOf(queuedCheck(scenarios["wrong-answer"]));
    expect(rows).toEqual([
      {
        kind: "notRun",
        from: 1,
        to: 2,
        names: [],
        reason: "waiting",
        started: false,
        failedAt: null,
      },
      { kind: "hidden", hidden: { kind: "submitOnly", total: 2 } },
    ]);
    expect(testsCount(testsView(queuedCheck(scenarios["wrong-answer"]), FIFO))).toBeNull();
  });

  it("show the running test and the ones to come", () => {
    const scenario = scenarios["run-passed"];
    const check = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
    const rows = rowsOf(check);
    expect(rows.slice(0, 2)).toEqual([
      { kind: "running", index: 1, name: "каждый вход по очереди" },
      expect.objectContaining({ kind: "notRun", from: 2, to: 2, reason: "waiting" }),
    ]);
    expect(testsCount(testsView(check, FIFO))).toEqual({
      passed: 0,
      total: 2,
      failed: false,
      finished: false,
    });
  });

  it("show the failed test with its mismatches", () => {
    const check = playCheck(scenarios["wrong-answer"]);
    expect(rowsOf(check)).toEqual([
      {
        kind: "passed",
        from: 1,
        to: 1,
        names: ["запись и чтение по порядку"],
        durationMs: null,
      },
      {
        kind: "failed",
        index: 2,
        id: "t2",
        name: "заполнение до full и опустошение",
        cycle: 30,
        mismatches: [
          {
            signal: "full",
            cycle: 30,
            expected: "1'h0",
            actual: "1'h1",
            hint: "full = 1, когда в очереди DEPTH слов",
          },
        ],
      },
      { kind: "hidden", hidden: { kind: "submitOnly", total: 2 } },
    ]);
    expect(testsCount(testsView(check, FIFO))).toEqual({
      passed: 1,
      total: 2,
      failed: true,
      finished: true,
    });
  });

  it("fold passed and not-run tests in a row; the unreported ones did not run either", () => {
    const check = withTests([
      test("t1", "passed", { duration_ms: 100 }),
      test("t2", "passed", { duration_ms: 200 }),
      test("t3", "passed", { duration_ms: 300 }),
      test("t4", "failed", { cycle: 143 }),
      test("t5", "not_run"),
      test("t6", "not_run"),
    ]);
    const rows = rowsOf(check, { ...FIFO, tests: { public: 8, hidden: 20 } });
    expect(rows).toEqual([
      {
        kind: "passed",
        from: 1,
        to: 3,
        names: ["name t1", "name t2", "name t3"],
        durationMs: 600,
      },
      { kind: "failed", index: 4, id: "t4", name: "name t4", cycle: 143, mismatches: [] },
      {
        kind: "notRun",
        from: 5,
        to: 8,
        names: ["name t5", "name t6"],
        reason: "afterFailure",
        started: false,
        failedAt: 4,
      },
      { kind: "hidden", hidden: { kind: "submitOnly", total: 20 } },
    ]);
  });

  it("have no time when a test has none", () => {
    const [passed] = rowsOf(
      withTests([test("t1", "passed", { duration_ms: 100 }), test("t2", "passed")]),
    );
    expect(passed).toMatchObject({ kind: "passed", from: 1, to: 2, durationMs: null });
  });

  it("name a test without a name by its id", () => {
    const [passed] = rowsOf(withTests([test("t1", "passed", { name: "" })]));
    expect(passed).toMatchObject({ names: ["t1"] });
  });

  it.each([
    ["compile-error", "skipped"],
    ["cancelled", "cancelled"],
    ["internal-error", "stopped"],
    ["output-limit", "stopped"],
  ] as const)("did not run in %s: %s", (name, reason) => {
    const [open] = rowsOf(playCheck(scenarios[name]));
    expect(open).toEqual({
      kind: "notRun",
      from: 1,
      to: 2,
      names: [],
      reason,
      started: false,
      failedAt: null,
    });
  });

  it("tell a test stopped in the middle", () => {
    const scenario = scenarios["output-limit"];
    const running = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
    const check: Check = {
      ...running,
      done: true,
      status: "limit_exceeded",
      stages: running.stages.map((stage) =>
        stage.key === "sim_run" ? { ...stage, status: "failed", failure_kind: "limit" } : stage,
      ),
    };
    expect(rowsOf(check)[0]).toEqual({
      kind: "notRun",
      from: 1,
      to: 1,
      names: ["запись и чтение по порядку"],
      reason: "stopped",
      started: true,
      failedAt: null,
    });
  });
});

describe("the hidden tests", () => {
  it("are counted while they run", () => {
    const scenario = scenarios.accepted;
    const check = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test" && event.test.id === "hidden-1"),
    );
    const rows = rowsOf(check);
    expect(rows).toEqual([
      expect.objectContaining({ kind: "passed", from: 1, to: 2 }),
      { kind: "hidden", hidden: { kind: "running", total: 2, passed: 0, index: 1 } },
    ]);
    expect(testsCount(testsView(check, FIFO))).toEqual({
      passed: 2,
      total: 4,
      failed: false,
      finished: false,
    });
  });

  it("wait while the open tests run", () => {
    const scenario = scenarios.accepted;
    const check = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
    expect(rowsOf(check).at(-1)).toEqual({
      kind: "hidden",
      hidden: { kind: "notRun", total: 2, passed: 0, reason: "waiting" },
    });
  });

  it("pass all together", () => {
    const check = playCheck(scenarios.accepted);
    expect(rowsOf(check).at(-1)).toEqual({ kind: "hidden", hidden: { kind: "passed", total: 2 } });
    expect(testsCount(testsView(check, FIFO))).toEqual({
      passed: 4,
      total: 4,
      failed: false,
      finished: true,
    });
  });

  it("show only the number of the failed one", () => {
    const check = playCheck(scenarios["wrong-answer-hidden"]);
    expect(rowsOf(check)).toEqual([
      expect.objectContaining({ kind: "passed", from: 1, to: 2 }),
      { kind: "hidden", hidden: { kind: "failed", total: 2, passed: 0, index: 1 } },
    ]);
    expect(testsCount(testsView(check, FIFO))).toEqual({
      passed: 2,
      total: 4,
      failed: true,
      finished: true,
    });
  });

  it("did not run after an open test failed", () => {
    const check = playCheck(scenarios["wrong-answer-hidden"]);
    const stopped: Check = {
      ...check,
      stages: check.stages.map((stage) =>
        stage.key === "sim_full"
          ? {
              ...stage,
              summary: {
                ...stage.summary,
                tests: [test("t1", "passed"), test("t2", "failed")],
                hidden_tests: { total: 2, passed: 0, failed_index: null },
              },
            }
          : stage,
      ),
    };
    expect(rowsOf(stopped).at(-1)).toEqual({
      kind: "hidden",
      hidden: { kind: "notRun", total: 2, passed: 0, reason: "afterFailure" },
    });
  });

  it("are left out when the problem has none", () => {
    const rows = rowsOf(playCheck(scenarios["wrong-answer"]), { ...FIFO, tests: { public: 2 } });
    expect(rows.some((row) => row.kind === "hidden")).toBe(false);
  });
});
