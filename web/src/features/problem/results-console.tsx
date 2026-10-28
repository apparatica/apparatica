"use client";

// The console tab of the results (FR-CON-*, mock-ups Bench, BenchRunning, ResultStates): the rows
// of the check in words, references to the solution leading to the editor.
import { useFormatter, useTranslations } from "next-intl";

import { Console, type ConsoleLine, type ConsoleTone } from "@/components/domain/console";
import { useKilobytes, useSeconds } from "@/components/domain/duration";
import { editorLanguage, isSolutionFile } from "@/features/editor/languages";
import type { Check, Stage } from "@/features/submission/machine";
import type { Connection } from "@/features/submission/stream";

import { type ConsoleRow, consoleRows, type LiveRow, liveRows } from "./console-view";
import type { ResultsProblem } from "./results-panel";

const SEVERITY_TONES = { error: "error", warning: "warning", info: "info" } as const;

const END_TONES: Record<Stage["status"], ConsoleTone> = {
  pending: "info",
  running: "info",
  passed: "ok",
  warning: "warning",
  failed: "error",
  skipped: "info",
  cancelled: "info",
  error: "error",
};

function useOutcome(): (stage: Stage) => string {
  const t = useTranslations("problem.results.console.end");
  const tl = useTranslations("problem.results.stage.limit");
  return (stage) => {
    const { caption } = stage.summary;
    switch (stage.status) {
      case "warning": {
        const count = stage.summary.diagnostics.filter((d) => d.severity === "warning").length;
        return count > 0 ? t("warnings", { count }) : (caption ?? t("passed"));
      }
      case "failed":
        switch (stage.failure_kind) {
          case "compile":
            return t("compile");
          case "forbidden":
            return t("forbidden");
          case "limit":
            return stage.limit == null ? t("limitOther") : t("limit", { limit: tl(stage.limit) });
          default:
            return caption ?? t("wrong");
        }
      case "cancelled":
        return t("cancelled");
      case "error":
        return stage.error_code == null ? t("error") : t("errorCode", { code: stage.error_code });
      default:
        return caption ?? t("passed");
    }
  };
}

function useLines(): {
  line: (row: ConsoleRow) => ConsoleLine;
  live: (row: LiveRow) => ConsoleLine;
} {
  const t = useTranslations("problem.results.console");
  const format = useFormatter();
  const seconds = useSeconds();
  const kilobytes = useKilobytes();
  const outcome = useOutcome();
  const text = (tone: ConsoleTone, value: string): ConsoleLine => ({
    kind: "line",
    tone,
    text: value,
  });
  return {
    line: (row) => {
      switch (row.kind) {
        case "separator":
          return { kind: "separator", tone: "info", text: row.stage };
        case "output":
          return text(row.tone, row.text);
        case "diagnostic": {
          const { file, line, col, message, severity } = row.diagnostic;
          const at = [file, line, col].filter((part) => part != null).join(":");
          return text(SEVERITY_TONES[severity], at ? t("diagnostic", { at, message }) : message);
        }
        case "passed": {
          const { hidden, from, to, total } = row;
          if (from === to) {
            return text("ok", t(hidden ? "hiddenPassedOne" : "passedOne", { index: from, total }));
          }
          return text("ok", t(hidden ? "hiddenPassedRange" : "passedRange", { from, to, total }));
        }
        case "failed": {
          const { place, name, cycle, mismatch } = row;
          const { index, total } = place;
          if (place.hidden) return text("error", t("hiddenFailed", { index, total }));
          if (mismatch !== null) {
            const { signal, expected, actual } = mismatch;
            return text(
              "error",
              t("failedMismatch", {
                index,
                total,
                name,
                cycle: mismatch.cycle,
                signal,
                expected,
                actual,
              }),
            );
          }
          if (cycle !== null) return text("error", t("failedCycle", { index, total, name, cycle }));
          return text("error", t("failed", { index, total, name }));
        }
        case "truncated":
          return text("warning", t("truncated", { size: kilobytes(row.limitKb) }));
        case "end": {
          const { stage } = row;
          const values = { stage: stage.key, outcome: outcome(stage) };
          return text(
            END_TONES[stage.status],
            stage.duration_ms == null
              ? t("end.line", values)
              : t("end.timed", { ...values, time: seconds(stage.duration_ms) }),
          );
        }
        case "lost":
          return {
            kind: "notice",
            tone: "warning",
            text: t("lost", {
              time: format.dateTime(row.at, {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              }),
            }),
          };
      }
    },
    live: (row) => {
      switch (row.kind) {
        case "waiting":
          return text("info", t("waiting"));
        case "test": {
          const { hidden, index, total } = row.place;
          return text("info", t(hidden ? "hiddenRunning" : "running", { index, total }));
        }
        case "step":
          return text("info", t("step", { name: row.name, time: seconds(row.elapsedMs) }));
      }
    },
  };
}

export interface ResultsConsoleProps {
  check: Check;
  connection: Connection | null;
  problem: ResultsProblem;
  /** The time of the running stage so far. */
  runningMs: number | null;
  onReveal: (line: number, column: number) => void;
}

export function ResultsConsole({
  check,
  connection,
  problem,
  runningMs,
  onReveal,
}: ResultsConsoleProps) {
  const t = useTranslations("problem.results.console");
  const { line, live } = useLines();
  const language = editorLanguage(problem.language);
  return (
    <Console
      className="h-full"
      lines={consoleRows(check, problem.tests, language).map(line)}
      live={liveRows(check, connection, problem.tests, runningMs).map(live)}
      empty={t("empty")}
      isLink={(file) => isSolutionFile(file, problem.language)}
      onLink={(link) => onReveal(link.line, link.column ?? 1)}
    />
  );
}
