import { describe, expect, it } from "vitest";

import { type Scenario, type ScenarioName, scenarios } from "@/mocks/scenarios";
import { foldEvents, queuedCheck } from "@/test/checks";

import { applyEvent, checkOf, compareEventIds, markLost } from "./machine";

/** The console lines of the last attempt of a scenario. */
function linesOf(scenario: Scenario): string[] {
  const attempts = scenario.events.flatMap(({ event }) =>
    "attempt" in event ? [event.attempt] : [],
  );
  const last = Math.max(...attempts);
  return scenario.events.flatMap(({ event }) =>
    event.type === "log" && event.attempt === last ? event.text.split("\n").slice(0, -1) : [],
  );
}

describe("every recorded check ends as stored", () => {
  for (const [name, scenario] of Object.entries(scenarios) as [ScenarioName, Scenario][]) {
    it(name, () => {
      const check = foldEvents(queuedCheck(scenario), scenario.events);
      const stored = scenario.submission;
      expect(check.status).toBe(stored.status);
      expect(check.verdict).toEqual(stored.verdict_detail);
      expect(check.done).toBe(true);
      expect(check.queue).toBeNull();
      expect(check.heartbeat).toBeNull();
      expect(check.runningSince).toBeNull();
      expect(check.stages.map((stage) => [stage.key, stage.status])).toEqual(
        stored.stages.map((stage) => [stage.key, stage.status]),
      );
      expect(check.stages.map((stage) => stage.summary.tests)).toEqual(
        stored.stages.map((stage) => stage.summary.tests),
      );
      expect(check.console.flatMap((entry) => (entry.kind === "line" ? [entry.text] : []))).toEqual(
        linesOf(scenario),
      );
      expect(check.lastEventId).toBe(scenario.events.at(-1)?.id);
    });
  }
});

it("waits in the queue, then runs", () => {
  const { events } = scenarios["wrong-answer"];
  let check = queuedCheck(scenarios["wrong-answer"]);
  expect(check).toMatchObject({ status: "queued", queue: { position: 3, etaS: 10 } });
  check = applyEvent(check, null, { type: "queue", position: 1, eta_s: 4 });
  expect(check.queue).toEqual({ position: 1, etaS: 4 });

  const start = events.findIndex(({ event }) => event.type === "stage_start");
  check = foldEvents(check, events.slice(0, start + 1));
  expect(check.status).toBe("running");
  expect(check.queue).toBeNull();
  expect(check.stages).toMatchObject([{ key: "precheck", status: "running" }]);
  // A late queue event of the API does not bring the queue back.
  check = applyEvent(check, null, { type: "queue", position: 1, eta_s: null });
  expect(check.queue).toBeNull();
});

it("replaces a test by its id while the stage runs", () => {
  const scenario = scenarios["wrong-answer"];
  const tests = scenario.events.filter(({ event }) => event.type === "test");
  const end = scenario.events.findIndex(
    ({ event }) => event.type === "stage_end" && event.result.key === "sim_run",
  );
  const check = foldEvents(queuedCheck(scenario), scenario.events.slice(0, end));
  const shown = check.stages.find((stage) => stage.key === "sim_run")?.summary.tests ?? [];
  expect(check.stages.at(-1)?.status).toBe("running");
  expect(tests.length).toBeGreaterThan(shown.length);
  expect(new Set(shown.map((test) => test.id)).size).toBe(shown.length);
  expect(shown.some((test) => test.status === "failed")).toBe(true);
});

it("starts the results over on a new attempt", () => {
  const scenario = scenarios.retry;
  const second = scenario.events.findIndex(
    ({ event }) => "attempt" in event && event.attempt === 2,
  );
  const before = foldEvents(queuedCheck(scenario), scenario.events.slice(0, second));
  expect(before.attempt).toBe(1);
  expect(before.stages.map((stage) => [stage.key, stage.status])).toEqual([
    ["precheck", "passed"],
    ["lint", "passed"],
    ["sim_run", "running"],
  ]);

  const after = foldEvents(before, scenario.events.slice(second, second + 1));
  expect(after).toMatchObject({ attempt: 2, status: "running", console: [] });
  expect(after.stages.map((stage) => [stage.key, stage.status])).toEqual([["precheck", "running"]]);
});

it("ignores events it already has", () => {
  const { events } = scenarios.accepted;
  const once = foldEvents(queuedCheck(scenarios.accepted), events);
  // A reconnect from an older id replays events: nothing changes.
  expect(foldEvents(once, events)).toBe(once);
  expect(compareEventIds("1793003352739-1", "1793003352739-10")).toBeLessThan(0);
  expect(compareEventIds("1793003352740-0", "1793003352739-10")).toBeGreaterThan(0);
});

it("ends a stage that was running when the check was cancelled", () => {
  const scenario = scenarios.accepted;
  const sim = scenario.events.findLastIndex(({ event }) => event.type === "stage_start");
  let check = foldEvents(queuedCheck(scenario), scenario.events.slice(0, sim + 1));
  const running = check.stages.at(-1)?.key;
  check = applyEvent(check, "9999999999999-0", {
    type: "finalized",
    status: "cancelled",
    verdict_detail: { first_failure: null, limit: null, warnings: [], error_codes: [] },
  });
  expect(check.status).toBe("cancelled");
  expect(check.stages.at(-1)).toMatchObject({ key: running, status: "cancelled" });
});

it("times the running stage from its start, then from its heartbeats", () => {
  let check = queuedCheck(scenarios.accepted);
  check = applyEvent(
    check,
    "1-0",
    { type: "stage_start", stage: "lint", stage_type: "lint", ordinal: 1, attempt: 1 },
    5000,
  );
  expect(check.runningSince).toBe(5000);
  check = applyEvent(
    check,
    "2-0",
    { type: "heartbeat", stage: "lint", elapsed_ms: 3000, note: null, attempt: 1 },
    9000,
  );
  expect(check.runningSince).toBe(6000);
  const [, lint] = scenarios.accepted.submission.stages;
  if (lint === undefined) throw new Error("no lint stage");
  check = applyEvent(
    check,
    "3-0",
    { type: "stage_end", result: { ...lint, limit: null, cached: false }, attempt: 1 },
    9500,
  );
  expect(check.runningSince).toBeNull();
});

it("keeps the output limit and the lost connection in the console", () => {
  const scenario = scenarios["output-limit"];
  const check = markLost(foldEvents(queuedCheck(scenario), scenario.events), 1000);
  expect(check.console.filter((entry) => entry.kind !== "line")).toEqual([
    { kind: "truncated", stage: "sim_run", limitKb: 16 },
    { kind: "lost", at: 1000 },
  ]);
});

it("restores a finished check and replays its console over it", () => {
  const scenario = scenarios["wrong-answer"];
  const restored = checkOf(scenario.submission);
  expect(restored).toMatchObject({ status: "wrong_answer", done: true, console: [] });
  expect(restored.stages.map((stage) => stage.status)).toEqual(
    scenario.submission.stages.map((stage) => stage.status),
  );
  const replayed = foldEvents(restored, scenario.events);
  expect(replayed.status).toBe("wrong_answer");
  expect(replayed.console.length).toBeGreaterThan(0);
  // While the archive replays, the stored verdict stays.
  const midway = foldEvents(restored, scenario.events.slice(0, 5));
  expect(midway.status).toBe("wrong_answer");
});
