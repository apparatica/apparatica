import { describe, expect, it } from "vitest";

import { applyEvent, checkOf } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import versions from "@/mocks/problem-versions.json";
import { type ScenarioName, scenarios } from "@/mocks/scenarios";
import { eventsUntil, playCheck, queuedCheck } from "@/test/checks";

import {
  editorDiagnostics,
  failureOf,
  firstError,
  lintWarnings,
  pipelineView,
  testProgress,
} from "./pipeline-view";

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
    { block: "lint", status: "pending", detail: { kind: "notRun" }, set: null, durationMs: null },
    { block: "sim", status: "pending", detail: { kind: "notRun" }, set: null, durationMs: null },
    { block: "synth", status: "pending", detail: { kind: "notRun" }, set: null, durationMs: null },
  ]);
});

it("waits with every block of a queued check", () => {
  expect(shape(pipelineView(FIFO.pipeline, queuedCheck(scenarios.accepted), null))).toEqual([
    ["lint", "pending", null],
    ["sim", "pending", null],
    ["synth", "pending", null],
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
    set: null,
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
        // The captions of the primary set, of the three sets the blocks checked.
        ["sim", "passed", { kind: "caption", text: "пройдено 4 из 4", sets: 3 }],
        // synth with netlist_sim: the metrics of synthesis, not the tests of the netlist
        [
          "synth",
          "passed",
          { kind: "caption", text: "0,592 нс, 1194,87 мкм², ячеек 526", sets: 3 },
        ],
      ],
    ],
    [
      "accepted-with-warnings",
      [
        ["lint", "warning", { kind: "warnings", count: 1 }],
        ["sim", "passed", { kind: "caption", text: "пройдено 4 из 4", sets: 3 }],
        ["synth", "passed", { kind: "caption", text: "0,172 нс, 41,76 мкм², ячеек 41", sets: 3 }],
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
      leaderboard: null,
    });
    expect(shape(pipelineView(FIFO.pipeline, check, null))).toEqual([
      ["lint", "pending", { kind: "notRun" }],
      ["sim", "pending", { kind: "notRun" }],
      ["synth", "pending", { kind: "notRun" }],
    ]);
  });
});

describe("parameter sets", () => {
  const scenario = scenarios["wrong-answer-param-set"];
  const NARROW = { id: "narrow", values: { WIDTH: 1, DEPTH: 2 } };

  it("plans every instance of a stage before the first check", () => {
    const keys = FIFO.pipeline.submit.map((stage) => stage.key);
    expect(keys).toContain("sim_full@narrow");
    expect(keys).toContain("netlist_sim@wide");
  });

  it("names the set of the instance that runs, and the next one between two", () => {
    const narrow = playCheck(
      scenario,
      eventsUntil(
        scenario,
        (event) => event.type === "stage_start" && event.stage === "sim_full@narrow",
      ),
    );
    expect(pipelineView(FIFO.pipeline, narrow, 100)[1]).toMatchObject({
      block: "sim",
      status: "running",
      detail: null,
      set: NARROW,
    });
    // The primary instance passed, the next one has not started: the block still runs.
    const between = playCheck(
      scenario,
      eventsUntil(
        scenario,
        (event) => event.type === "stage_end" && event.result.key === "sim_full",
      ),
    );
    expect(pipelineView(FIFO.pipeline, between, null)[1]).toMatchObject({
      status: "running",
      set: NARROW,
    });
    // The primary instance runs: no set to name.
    const primary = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "stage_start" && event.stage === "sim_full"),
    );
    expect(pipelineView(FIFO.pipeline, primary, 100)[1]).toMatchObject({ set: null });
  });

  it("is failed by the instance of an extra set, the worst of them", () => {
    const blocks = pipelineView(FIFO.pipeline, playCheck(scenario), null);
    expect(blocks.map(({ block, status, set }) => [block, status, set])).toEqual([
      ["lint", "passed", null],
      ["sim", "failed", NARROW],
      ["synth", "skipped", null],
    ]);
    expect(pipelineView(FIFO.pipeline, checkOf(scenario.submission), null)).toEqual(blocks);
    expect(failureOf(playCheck(scenario))).toMatchObject({
      kind: "test",
      name: "запись и чтение по порядку",
    });
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

it("marks in the editor the diagnostics of precheck and lint on the solution", () => {
  expect(editorDiagnostics(playCheck(scenarios["compile-error"]), "systemverilog")).toEqual([
    expect.objectContaining({ severity: "error", line: 16, col: 19, file: "solution.sv" }),
  ]);
  expect(
    editorDiagnostics(playCheck(scenarios["accepted-with-warnings"]), "systemverilog"),
  ).toEqual([expect.objectContaining({ severity: "warning", line: 13, code: "WIDTHTRUNC" })]);
  // Another language knows no solution file; no check, no markers.
  expect(editorDiagnostics(playCheck(scenarios["compile-error"]), "vhdl")).toEqual([]);
  expect(editorDiagnostics(null, "systemverilog")).toEqual([]);
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
