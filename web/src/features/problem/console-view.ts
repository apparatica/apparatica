// What the console shows of a check (FR-CON-01/04/05): the rows of its stream in order, with the
// passed tests in a row folded into one, and under them what goes on right now. The judge streams
// the raw output of the tools; the starts and ends of the stages, the tests and the diagnostics
// that the output does not print (precheck) come from the events.
import type { ConsoleTone } from "@/components/domain/console";
import type { EditorLanguage } from "@/features/editor/languages";
import type { Check, ConsoleEntry, Stage, TestCase } from "@/features/submission/machine";
import type { Connection } from "@/features/submission/stream";
import type { Schemas } from "@/lib/api/client";

import { OPEN_GROUP } from "./pipeline-view";

export interface TestPlace {
  /** Hidden tests are counted apart and never named. */
  hidden: boolean;
  /** 1-based, among the tests of its group in the check. */
  index: number;
  total: number;
}

export type ConsoleRow =
  | { kind: "separator"; stage: string }
  | { kind: "output"; text: string; tone: ConsoleTone }
  /** A message of a tool that its output did not print. */
  | { kind: "diagnostic"; diagnostic: Schemas["Diagnostic"] }
  /** Passed tests in a row: `from` to `to` of their group. */
  | { kind: "passed"; hidden: boolean; from: number; to: number; total: number }
  | {
      kind: "failed";
      place: TestPlace;
      name: string;
      cycle: number | null;
      mismatch: Schemas["Mismatch"] | null;
    }
  | { kind: "truncated"; limitKb: number }
  | { kind: "end"; stage: Stage }
  | { kind: "lost"; at: number };

export type LiveRow =
  | { kind: "waiting" }
  | { kind: "test"; place: TestPlace }
  /** The running step and its time so far: the heartbeat note, or the stage. */
  | { kind: "step"; name: string; elapsedMs: number };

const outputTone = (
  entry: Extract<ConsoleEntry, { kind: "line" }>,
  language: EditorLanguage,
): ConsoleTone => {
  if (entry.ch === "sys") return "info";
  return language.outputTones.find(({ start }) => start.test(entry.text))?.tone ?? "plain";
};

const isHidden = (test: TestCase) => test.group !== OPEN_GROUP;

/** The diagnostics of a stage that its output lines do not mention. */
function unprinted(stage: Stage, printed: readonly string[]): Schemas["Diagnostic"][] {
  return stage.summary.diagnostics.filter((diagnostic) => {
    const mark =
      diagnostic.file != null && diagnostic.line != null
        ? `${diagnostic.file}:${diagnostic.line}`
        : diagnostic.message;
    return !printed.some((line) => line.includes(mark));
  });
}

/** The test as the end of its stage reported it: with the mismatches the stream may lack. */
function finalTest(check: Check, stage: string, test: TestCase): TestCase {
  const reported = check.stages
    .find((item) => item.key === stage)
    ?.summary.tests.find((item) => item.id === test.id);
  return reported?.status === test.status ? reported : test;
}

export function consoleRows(
  check: Check,
  groups: Record<string, number>,
  language: EditorLanguage,
): ConsoleRow[] {
  const rows: ConsoleRow[] = [];
  const printed = new Map<string, string[]>();
  const counted = new Map<string, number>();
  for (const entry of check.console) {
    switch (entry.kind) {
      case "stage":
        rows.push({ kind: "separator", stage: entry.stage });
        break;
      case "line":
        printed.set(entry.stage, [...(printed.get(entry.stage) ?? []), entry.text]);
        rows.push({ kind: "output", text: entry.text, tone: outputTone(entry, language) });
        break;
      case "test": {
        const hidden = isHidden(entry.test);
        const key = `${entry.stage}/${entry.test.group}`;
        const index = (counted.get(key) ?? 0) + 1;
        counted.set(key, index);
        const total = Math.max(groups[entry.test.group] ?? 0, index);
        const last = rows.at(-1);
        if (entry.test.status === "passed") {
          if (last?.kind === "passed" && last.hidden === hidden && last.to === index - 1) {
            rows[rows.length - 1] = { ...last, to: index, total };
          } else {
            rows.push({ kind: "passed", hidden, from: index, to: index, total });
          }
          break;
        }
        const test = finalTest(check, entry.stage, entry.test);
        const mismatch = test.mismatches[0] ?? null;
        rows.push({
          kind: "failed",
          place: { hidden, index, total },
          name: test.name || test.id,
          cycle: mismatch?.cycle ?? test.cycle ?? null,
          mismatch,
        });
        break;
      }
      case "truncated":
        rows.push({ kind: "truncated", limitKb: entry.limitKb });
        break;
      case "end":
        for (const diagnostic of unprinted(entry.stage, printed.get(entry.stage.key) ?? [])) {
          rows.push({ kind: "diagnostic", diagnostic });
        }
        rows.push({ kind: "end", stage: entry.stage });
        break;
      case "lost":
        rows.push({ kind: "lost", at: entry.at });
        break;
    }
  }
  return rows;
}

/** What goes on right now: nothing once the check has ended. */
export function liveRows(
  check: Check,
  connection: Connection | null,
  groups: Record<string, number>,
  runningMs: number | null,
): LiveRow[] {
  if (check.done) return [];
  const lost =
    connection?.state === "waiting" ||
    connection?.state === "failed" ||
    (connection?.state === "connecting" && connection.lostAt !== null);
  if (lost) return [{ kind: "waiting" }];
  const stage = check.stages.find((item) => item.status === "running");
  if (stage === undefined) return [];
  const rows: LiveRow[] = [];
  const running = stage.summary.tests.find((test) => test.status === "running");
  if (running !== undefined) {
    const group = stage.summary.tests.filter((test) => test.group === running.group);
    const index = group.indexOf(running) + 1;
    rows.push({
      kind: "test",
      place: {
        hidden: isHidden(running),
        index,
        total: Math.max(groups[running.group] ?? 0, index),
      },
    });
  }
  if (runningMs !== null) {
    const note = check.heartbeat?.stage === stage.key ? check.heartbeat.note : null;
    rows.push({ kind: "step", name: note ?? stage.key, elapsedMs: runningMs });
  }
  return rows;
}
