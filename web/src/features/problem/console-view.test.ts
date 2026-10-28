import { describe, expect, it } from "vitest";

import { editorLanguage } from "@/features/editor/languages";
import { markLost } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import versions from "@/mocks/problem-versions.json";
import { scenarios } from "@/mocks/scenarios";
import { eventsUntil, playCheck } from "@/test/checks";

import { type ConsoleRow, consoleRows, liveRows } from "./console-view";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];
const SV = editorLanguage("systemverilog");

/** The rows without the output lines of the tools. */
const own = (rows: ConsoleRow[]) => rows.filter((row) => row.kind !== "output");
const kinds = (rows: ConsoleRow[]) =>
  own(rows).map((row) => (row.kind === "separator" || row.kind === "end" ? row : row.kind));

describe("the rows of a check", () => {
  it("open and close each stage and fold the passed tests in a row", () => {
    const rows = consoleRows(playCheck(scenarios.accepted), FIFO.tests, SV);
    expect(
      own(rows).map((row) => {
        if (row.kind === "separator") return `── ${row.stage}`;
        if (row.kind === "end") return `${row.stage.key}: ${row.stage.status}`;
        return row;
      }),
    ).toEqual([
      "── precheck",
      "precheck: passed",
      "── lint",
      "lint: passed",
      "── sim_full",
      { kind: "passed", hidden: false, from: 1, to: 2, total: 2 },
      { kind: "passed", hidden: true, from: 1, to: 2, total: 2 },
      "sim_full: passed",
    ]);
  });

  it("colour the warnings of the tools and do not repeat the diagnostics they printed", () => {
    const rows = consoleRows(playCheck(scenarios["accepted-with-warnings"]), FIFO.tests, SV);
    const output = rows.filter((row) => row.kind === "output");
    expect(output.find((row) => row.text.startsWith("%Warning-WIDTHTRUNC"))?.tone).toBe("warning");
    expect(output.find((row) => row.text.startsWith("- Verilator:"))?.tone).toBe("plain");
    expect(rows.some((row) => row.kind === "diagnostic")).toBe(false);
  });

  it("print a diagnostic the output did not", () => {
    expect(kinds(consoleRows(playCheck(scenarios["compile-error"]), FIFO.tests, SV))).toEqual([
      { kind: "separator", stage: "precheck" },
      "diagnostic",
      expect.objectContaining({ kind: "end" }),
    ]);
    const [, diagnostic] = consoleRows(playCheck(scenarios["compile-error"]), FIFO.tests, SV);
    expect(diagnostic).toMatchObject({
      kind: "diagnostic",
      diagnostic: { file: "solution.sv", line: 16, col: 19, message: "expected ';'" },
    });
  });

  it("tell the failed open test with its first mismatch from the end of the stage", () => {
    const rows = consoleRows(playCheck(scenarios["wrong-answer"]), FIFO.tests, SV);
    expect(rows.filter((row) => row.kind === "passed" || row.kind === "failed")).toEqual([
      { kind: "passed", hidden: false, from: 1, to: 1, total: 2 },
      {
        kind: "failed",
        place: { hidden: false, index: 2, total: 2 },
        name: "заполнение до full и опустошение",
        cycle: 30,
        mismatch: {
          signal: "full",
          cycle: 30,
          expected: "1'h0",
          actual: "1'h1",
          hint: "full = 1, когда в очереди DEPTH слов",
        },
      },
    ]);
  });

  it("tell only the number of a failed hidden test", () => {
    const rows = consoleRows(playCheck(scenarios["wrong-answer-hidden"]), { public: 2 }, SV);
    expect(rows.find((row) => row.kind === "failed")).toEqual({
      kind: "failed",
      place: { hidden: true, index: 1, total: 1 },
      name: "hidden-1",
      cycle: null,
      mismatch: null,
    });
  });

  it("keep the output limit, the system lines and the lost connection", () => {
    const limited = consoleRows(playCheck(scenarios["output-limit"]), FIFO.tests, SV);
    expect(kinds(limited).slice(-2)).toEqual([
      "truncated",
      expect.objectContaining({ kind: "end", stage: expect.objectContaining({ limit: "output" }) }),
    ]);
    const cancelled = consoleRows(markLost(playCheck(scenarios.cancelled), 5), FIFO.tests, SV);
    expect(cancelled.findLast((row) => row.kind === "output")).toEqual({
      kind: "output",
      text: "cancelled",
      tone: "info",
    });
    expect(cancelled.at(-1)).toEqual({ kind: "lost", at: 5 });
  });
});

describe("what goes on right now", () => {
  const scenario = scenarios["run-passed"];
  const running = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "test" && event.test.status === "running"),
  );

  it("is the running test and the time of the stage", () => {
    expect(liveRows(running, { state: "open" }, FIFO.tests, 1400)).toEqual([
      { kind: "test", place: { hidden: false, index: 1, total: 2 } },
      { kind: "step", name: "sim_run", elapsedMs: 1400 },
    ]);
  });

  it("names the step by the note of its heartbeat", () => {
    const check = {
      ...running,
      heartbeat: {
        type: "heartbeat" as const,
        stage: "sim_run",
        elapsed_ms: 4200,
        note: "компиляция C++",
        attempt: 1,
      },
    };
    expect(liveRows(check, { state: "open" }, FIFO.tests, 4200).at(-1)).toEqual({
      kind: "step",
      name: "компиляция C++",
      elapsedMs: 4200,
    });
  });

  it("is waiting for the stream after a loss", () => {
    const waiting = { state: "waiting", retry: 1, retries: 5, at: 9, lostAt: 1 } as const;
    expect(liveRows(running, waiting, FIFO.tests, 1400)).toEqual([{ kind: "waiting" }]);
  });

  it("is nothing once the check has ended", () => {
    expect(liveRows(playCheck(scenario), { state: "closed" }, FIFO.tests, null)).toEqual([]);
  });
});
