import { describe, expect, it } from "vitest";

import { applyEvent, checkOf } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import versions from "@/mocks/problem-versions.json";
import { type ScenarioName, scenarios } from "@/mocks/scenarios";
import { eventsUntil, playCheck, queuedCheck } from "@/test/checks";

import { failureOf, firstError, lintWarnings, pipelineView, testProgress } from "./pipeline-view";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];

const durations = (name: ScenarioName, ...keys: string[]) =>
  scenarios[name].submission.stages
    .filter((stage) => keys.includes(stage.key))
    .reduce((sum, stage) => sum + (stage.duration_ms ?? 0), 0);

const shape = (blocks: ReturnType<typeof pipelineView>) =>
  blocks.map(({ block, status, detail }) => [block, status, detail]);

it("draws the stages of Run and Submit as not run before the first check", () => {
  expect(pipelineView(FIFO.pipeline, null, null)).toEqual([
    { block: "lint", status: "pending", detail: { kind: "notRun" }, durationMs: null },
    { block: "sim", status: "pending", detail: { kind: "notRun" }, durationMs: null },
  ]);
});

it("waits with every block of a queued check", () => {
  expect(shape(pipelineView(FIFO.pipeline, queuedCheck(scenarios.accepted), null))).toEqual([
    ["lint", "pending", null],
    ["sim", "pending", null],
  ]);
});

it("runs the lint block from precheck to the end of lint, timing it", () => {
  const scenario = scenarios.accepted;
  const precheck = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "stage_start"),
  );
  expect(pipelineView(FIFO.pipeline, precheck, 400)[0]).toEqual({
    block: "lint",
    status: "running",
    detail: null,
    durationMs: 400,
  });
  // precheck ended, lint not started yet: the block still runs.
  const between = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "stage_end"),
  );
  expect(pipelineView(FIFO.pipeline, between, null)[0]).toMatchObject({
    status: "running",
    durationMs: durations("accepted", "precheck"),
  });
  const lint = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "stage_start" && event.stage === "lint"),
  );
  expect(pipelineView(FIFO.pipeline, lint, 300)[0]).toMatchObject({
    status: "running",
    durationMs: durations("accepted", "precheck") + 300,
  });
});

describe("a finished check", () => {
  it.each<[ScenarioName, unknown[]]>([
    [
      "accepted",
      [
        ["lint", "passed", null],
        ["sim", "passed", { kind: "caption", text: "пройдено 4 из 4" }],
      ],
    ],
    [
      "accepted-with-warnings",
      [
        ["lint", "warning", { kind: "warnings", count: 1 }],
        ["sim", "passed", { kind: "caption", text: "пройдено 4 из 4" }],
      ],
    ],
    [
      "wrong-answer",
      [
        ["lint", "passed", null],
        [
          "sim",
          "failed",
          { kind: "caption", text: "упал тест заполнение до full и опустошение, такт 30" },
        ],
      ],
    ],
    [
      "compile-error",
      [
        ["lint", "failed", null],
        ["sim", "skipped", null],
      ],
    ],
    [
      "output-limit",
      [
        ["lint", "passed", null],
        ["sim", "warning", { kind: "limit", limit: "output" }],
      ],
    ],
    [
      "cancelled",
      [
        ["lint", "passed", null],
        ["sim", "cancelled", null],
      ],
    ],
    [
      "internal-error",
      [
        ["lint", "passed", null],
        ["sim", "error", null],
      ],
    ],
  ])("%s", (name, expected) => {
    const blocks = pipelineView(FIFO.pipeline, playCheck(scenarios[name]), null);
    expect(shape(blocks)).toEqual(expected);
    // Stored and streamed, the check looks the same.
    expect(pipelineView(FIFO.pipeline, checkOf(scenarios[name].submission), null)).toEqual(blocks);
  });

  it("times a block by its stages and a platform failure not at all", () => {
    const [lint, sim] = pipelineView(FIFO.pipeline, playCheck(scenarios["internal-error"]), null);
    expect(lint?.durationMs).toBe(durations("internal-error", "precheck", "lint"));
    expect(sim?.durationMs).toBeNull();
  });

  it("has not run the stages a check cancelled in the queue never reached", () => {
    const check = applyEvent(queuedCheck(scenarios.accepted), "1-0", {
      type: "finalized",
      status: "cancelled",
      verdict_detail: { first_failure: null, limit: null, warnings: [], error_codes: [] },
    });
    expect(shape(pipelineView(FIFO.pipeline, check, null))).toEqual([
      ["lint", "pending", { kind: "notRun" }],
      ["sim", "pending", { kind: "notRun" }],
    ]);
  });
});

it("finds the failed open test and its first mismatch", () => {
  expect(failureOf(playCheck(scenarios["wrong-answer"]))).toEqual({
    kind: "test",
    name: "заполнение до full и опустошение",
    cycle: 30,
    mismatch: {
      signal: "full",
      cycle: 30,
      expected: "1'h0",
      actual: "1'h1",
      hint: "full = 1, когда в очереди DEPTH слов",
    },
  });
});

it("tells only the number of a failed hidden test", () => {
  expect(failureOf(playCheck(scenarios["wrong-answer-hidden"]))).toEqual({
    kind: "hidden",
    index: 1,
    total: 2,
  });
});

it("finds the first error of a compile error", () => {
  expect(firstError(playCheck(scenarios["compile-error"]))).toMatchObject({
    line: 16,
    message: "expected ';'",
    file: "solution.sv",
  });
});

it("counts the lint warnings", () => {
  expect(lintWarnings(playCheck(scenarios["accepted-with-warnings"]))).toBe(1);
  expect(lintWarnings(playCheck(scenarios.accepted))).toBe(0);
});

it("counts the tests of a running simulation against its groups", () => {
  const scenario = scenarios["run-passed"];
  const first = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "test"),
  );
  expect(testProgress(first, FIFO.tests)).toEqual({ current: 1, total: 2 });
  const submit = scenarios.accepted;
  const hidden = playCheck(
    submit,
    eventsUntil(submit, (event) => event.type === "test" && event.test.group === "hidden"),
  );
  expect(testProgress(hidden, FIFO.tests)).toEqual({ current: 3, total: 4 });
  expect(testProgress(playCheck(scenario), FIFO.tests)).toBeNull();
});
