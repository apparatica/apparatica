// What the tests tab shows of a check (FR-TST-*): the open tests of each simulation stage, passed
// and not-run tests in a row folded into one row, and the hidden tests as one row with counters
// only (specs/06 §3.4). The names of the open tests come from the check; before they come, only
// their number from the problem is known.
import type { Check, Stage, TestCase } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";

import { OPEN_GROUP, pendingStage } from "./pipeline-view";

/** Why tests did not run, or, for a test that started, why it did not finish. */
export type NotRunReason =
  /** The stage has not got to them yet. */
  | "waiting"
  /** An earlier test failed and the run stopped. */
  | "afterFailure"
  /** The stage did not run: an earlier stage failed. */
  | "skipped"
  | "cancelled"
  /** A limit or a platform failure stopped the stage. */
  | "stopped";

export type TestsRow =
  /** Passed tests in a row, `from` to `to` (1-based, among the open tests). */
  | { kind: "passed"; from: number; to: number; names: string[]; durationMs: number | null }
  | { kind: "running"; index: number; name: string }
  | {
      kind: "failed";
      index: number;
      /** The id of the test: the trace of the check names it. */
      id: string;
      name: string;
      cycle: number | null;
      mismatches: Schemas["Mismatch"][];
    }
  /** Tests that did not run; `names` is empty for tests the check has not reported. `started`:
   * one test that ran and was stopped. */
  | {
      kind: "notRun";
      from: number;
      to: number;
      names: string[];
      reason: NotRunReason;
      started: boolean;
      /** For `afterFailure`: the test that stopped the run. */
      failedAt: number | null;
    }
  | { kind: "hidden"; hidden: HiddenView };

export type HiddenView =
  /** Run: hidden tests run only on Submit. */
  | { kind: "submitOnly"; total: number }
  | { kind: "running"; total: number; passed: number; index: number }
  | { kind: "passed"; total: number }
  | { kind: "failed"; total: number; passed: number; index: number }
  | { kind: "notRun"; total: number; passed: number; reason: NotRunReason };

export interface TestsSection {
  stage: string;
  rows: TestsRow[];
}

/** The counter of the tab: passed of all, and whether one failed. */
export interface TestsCount {
  passed: number;
  total: number;
  failed: boolean;
  /** Every test of the check is known. */
  finished: boolean;
}

const isOpen = (test: TestCase) => test.group === OPEN_GROUP;
const nameOf = (test: TestCase) => test.name || test.id;

function openTotal(groups: Record<string, number>): number {
  return groups[OPEN_GROUP] ?? 0;
}

function hiddenTotal(groups: Record<string, number>): number {
  return Object.entries(groups).reduce(
    (sum, [group, count]) => (group === OPEN_GROUP ? sum : sum + count),
    0,
  );
}

/** The stages of the check that run tests, in pipeline order: those not started yet too. */
function simStages(check: Check, pipeline: Schemas["PipelineInfo"]): Stage[] {
  return pipeline[check.kind].flatMap(({ key, type }, ordinal) =>
    type === "sim"
      ? [check.stages.find((stage) => stage.key === key) ?? pendingStage(key, type, ordinal)]
      : [],
  );
}

/** Why the tests of a stage that will not run them any more did not run. */
function reasonOf(check: Check, stage: Stage): NotRunReason {
  if (stage.status === "skipped") {
    return stage.summary.skip_reason === "cancelled" ? "cancelled" : "skipped";
  }
  if (stage.status === "cancelled" || check.status === "cancelled") return "cancelled";
  if (stage.status === "pending") return check.status === "internal_error" ? "stopped" : "skipped";
  if (stage.status === "failed" && stage.failure_kind === "wrong") return "afterFailure";
  return "stopped";
}

/** The stage will run no more tests. */
const ended = (check: Check, stage: Stage) =>
  stage.status !== "running" && (stage.status !== "pending" || check.done);

function sumDurations(tests: readonly TestCase[]): number | null {
  if (tests.some((test) => test.duration_ms == null)) return null;
  return tests.reduce((sum, test) => sum + (test.duration_ms ?? 0), 0);
}

function openRows(check: Check, stage: Stage, groups: Record<string, number>): TestsRow[] {
  const tests = stage.summary.tests.filter(isOpen);
  const rows: TestsRow[] = [];
  const over = ended(check, stage);
  const reason = over ? reasonOf(check, stage) : "waiting";
  let failedAt: number | null = null;
  let passed: TestCase[] = [];
  tests.forEach((test, at) => {
    const index = at + 1;
    const last = rows.at(-1);
    switch (test.status) {
      case "passed":
        if (last?.kind === "passed" && last.to === index - 1) {
          passed = [...passed, test];
          rows[rows.length - 1] = {
            ...last,
            to: index,
            names: [...last.names, nameOf(test)],
            durationMs: sumDurations(passed),
          };
        } else {
          passed = [test];
          rows.push({
            kind: "passed",
            from: index,
            to: index,
            names: [nameOf(test)],
            durationMs: sumDurations(passed),
          });
        }
        break;
      case "failed":
        failedAt ??= index;
        rows.push({
          kind: "failed",
          index,
          id: test.id,
          name: nameOf(test),
          cycle: test.mismatches[0]?.cycle ?? test.cycle ?? null,
          mismatches: test.mismatches,
        });
        break;
      case "running":
        // A stage that ended with a test still running was stopped in it.
        rows.push(
          over
            ? {
                kind: "notRun",
                from: index,
                to: index,
                names: [nameOf(test)],
                reason: reason === "afterFailure" ? "stopped" : reason,
                started: true,
                failedAt: null,
              }
            : { kind: "running", index, name: nameOf(test) },
        );
        break;
      case "not_run": {
        const why = failedAt === null ? reason : "afterFailure";
        if (last?.kind === "notRun" && !last.started && last.to === index - 1) {
          rows[rows.length - 1] = { ...last, to: index, names: [...last.names, nameOf(test)] };
        } else {
          rows.push({
            kind: "notRun",
            from: index,
            to: index,
            names: [nameOf(test)],
            reason: why,
            started: false,
            failedAt: why === "afterFailure" ? failedAt : null,
          });
        }
        break;
      }
    }
  });
  // The tests the check has not reported: still to come, or never run.
  const total = Math.max(openTotal(groups), tests.length);
  if (total > tests.length) {
    const why = failedAt === null ? reason : "afterFailure";
    const last = rows.at(-1);
    const from = tests.length + 1;
    if (last?.kind === "notRun" && !last.started && last.reason === why) {
      rows[rows.length - 1] = { ...last, to: total };
    } else {
      rows.push({
        kind: "notRun",
        from,
        to: total,
        names: [],
        reason: why,
        started: false,
        failedAt: why === "afterFailure" ? failedAt : null,
      });
    }
  }
  return rows;
}

function hiddenOf(check: Check, stage: Stage, groups: Record<string, number>): HiddenView | null {
  const counted = stage.summary.hidden_tests;
  const total = counted?.total ?? hiddenTotal(groups);
  if (total === 0) return null;
  if (check.kind === "run") return { kind: "submitOnly", total };
  if (counted != null) {
    if (counted.failed_index != null) {
      return { kind: "failed", total, passed: counted.passed, index: counted.failed_index };
    }
    if (counted.passed >= total) return { kind: "passed", total };
    return { kind: "notRun", total, passed: counted.passed, reason: reasonOf(check, stage) };
  }
  // While the stage runs, its hidden tests come anonymous in the stream.
  const tests = stage.summary.tests.filter((test) => !isOpen(test));
  const passed = tests.filter((test) => test.status === "passed").length;
  if (!ended(check, stage)) {
    const running = tests.findIndex((test) => test.status === "running");
    if (running === -1) return { kind: "notRun", total, passed, reason: "waiting" };
    return { kind: "running", total, passed, index: running + 1 };
  }
  return { kind: "notRun", total, passed, reason: reasonOf(check, stage) };
}

/** The tests of a check, a section for each of its simulation stages. */
export function testsView(
  check: Check,
  problem: Pick<Schemas["ProblemDetail"], "pipeline" | "tests">,
): TestsSection[] {
  return simStages(check, problem.pipeline).map((stage) => {
    const hidden = hiddenOf(check, stage, problem.tests);
    const rows = openRows(check, stage, problem.tests);
    return {
      stage: stage.key,
      rows: hidden === null ? rows : [...rows, { kind: "hidden", hidden }],
    };
  });
}

/** The counter of the tests tab; null before the tests start. */
export function testsCount(sections: readonly TestsSection[]): TestsCount | null {
  let passed = 0;
  let total = 0;
  let failed = false;
  let started = false;
  let finished = true;
  for (const row of sections.flatMap((section) => section.rows)) {
    switch (row.kind) {
      case "passed":
        started = true;
        passed += row.to - row.from + 1;
        total += row.to - row.from + 1;
        break;
      case "failed":
        started = true;
        failed = true;
        total += 1;
        break;
      case "running":
        started = true;
        finished = false;
        total += 1;
        break;
      case "notRun":
        started ||= row.started;
        finished &&= row.reason !== "waiting";
        total += row.to - row.from + 1;
        break;
      case "hidden": {
        const { hidden } = row;
        if (hidden.kind === "submitOnly") break;
        total += hidden.total;
        if (hidden.kind === "passed") {
          started = true;
          passed += hidden.total;
          break;
        }
        passed += hidden.passed;
        started ||= hidden.passed > 0 || hidden.kind !== "notRun";
        failed ||= hidden.kind === "failed";
        finished &&=
          hidden.kind !== "running" && !(hidden.kind === "notRun" && hidden.reason === "waiting");
        break;
      }
    }
  }
  return started ? { passed, total, failed, finished } : null;
}
