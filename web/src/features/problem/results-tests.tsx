"use client";

// The tests tab of the results (FR-TST-*, sheets CmpB and ResultTabs): the rows of the tests in
// words, the counter of the tab.
import { useTranslations } from "next-intl";

import { useSeconds } from "@/components/domain/duration";
import { TestList, type TestRowView } from "@/components/domain/test-list";
import type { Check } from "@/features/submission/machine";
import { cn } from "@/lib/utils";

import type { HiddenView, NotRunReason, TestsCount, TestsRow, TestsSection } from "./tests-view";

function useRows(seed: string): (row: TestsRow, at: number) => TestRowView {
  const t = useTranslations("problem.results.tests");
  const seconds = useSeconds();
  const titleOf = (index: number, name: string | undefined) =>
    name === undefined ? t("oneUnnamed", { index }) : t("one", { index, name });
  const why = (reason: NotRunReason, failedAt: number | null) =>
    reason === "afterFailure" && failedAt !== null
      ? t("why.afterFailureAt", { index: failedAt })
      : t(`why.${reason}`);
  const notRun = (reason: NotRunReason, count: number, failedAt: number | null) =>
    reason === "waiting"
      ? t("waiting", { count })
      : t("notRun", { count, why: why(reason, failedAt) });
  const hidden = (view: HiddenView): Pick<TestRowView, "status" | "caption"> => {
    switch (view.kind) {
      case "submitOnly":
        return { status: "notRun", caption: t("hidden.submitOnly") };
      case "running":
        return { status: "running", caption: t("hidden.running", view) };
      case "passed":
        return { status: "passed", caption: t("hidden.passed", view) };
      case "failed":
        return { status: "failed", caption: t("hidden.failed", view) };
      case "notRun":
        return {
          status: "notRun",
          caption:
            view.passed === 0 || view.reason === "waiting"
              ? notRun(view.reason, view.total, null)
              : t("hidden.rest", { ...view, why: why(view.reason, null) }),
        };
    }
  };
  return (row, at) => {
    const key = `${row.kind}-${at}`;
    switch (row.kind) {
      case "passed": {
        const aside = row.durationMs === null ? undefined : seconds(row.durationMs);
        if (row.from === row.to) {
          return {
            key,
            status: "passed",
            title: titleOf(row.from, row.names[0]),
            caption: t("passed"),
            aside,
          };
        }
        return {
          key,
          status: "passed",
          title: t("range", { from: row.from, to: row.to }),
          caption: row.names.join(", "),
          aside,
        };
      }
      case "running":
        return {
          key,
          status: "running",
          title: titleOf(row.index, row.name),
          caption: t("running"),
        };
      case "failed": {
        const hints = [
          ...new Set(row.mismatches.flatMap(({ hint }) => (hint ? [t("hint", { hint })] : []))),
        ];
        return {
          key,
          status: "failed",
          title: titleOf(row.index, row.name),
          caption: row.cycle === null ? t("failed") : t("failedCycle", { cycle: row.cycle }),
          aside: row.cycle === null ? undefined : t("cycle", { cycle: row.cycle }),
          mismatches: row.mismatches,
          notes: [...hints, t("seed", { name: row.name, seed })],
        };
      }
      case "notRun": {
        const count = row.to - row.from + 1;
        const caption = row.started
          ? t("interrupted", { why: why(row.reason, null) })
          : notRun(row.reason, count, row.failedAt);
        if (count === 1) {
          return { key, status: "notRun", title: titleOf(row.from, row.names[0]), caption };
        }
        return {
          key,
          status: "notRun",
          title: t("range", { from: row.from, to: row.to }),
          caption,
          count,
        };
      }
      case "hidden":
        return {
          key,
          hidden: true,
          title: t("hiddenTitle", { total: row.hidden.total }),
          ...hidden(row.hidden),
        };
    }
  };
}

const COUNT_TONES = {
  failed: "bg-ers text-er",
  passed: "bg-oks text-ok",
  running: "bg-sf2 text-mu",
};

/** "6/12" right of the tab title: red with a failed test, green when all passed. */
export function TestsCounter({ count }: { count: TestsCount }) {
  const tone = count.failed
    ? "failed"
    : count.finished && count.passed === count.total
      ? "passed"
      : "running";
  return (
    <span className={cn("rounded-xs px-1 font-mono text-[11px]", COUNT_TONES[tone])}>
      {count.passed}/{count.total}
    </span>
  );
}

export interface ResultsTestsProps {
  check: Check;
  sections: readonly TestsSection[];
}

export function ResultsTests({ check, sections }: ResultsTestsProps) {
  const t = useTranslations("problem.results.tests");
  const rowOf = useRows(check.seed);
  const titleOf = (section: TestsSection) => {
    const hidden = check.kind === "submit" && section.rows.some((row) => row.kind === "hidden");
    const title = t(check.kind === "run" ? "titleRun" : hidden ? "titleSubmit" : "titleSubmitOpen");
    return sections.length > 1 ? t("titleStage", { title, stage: section.stage }) : title;
  };
  return (
    <div className="h-full overflow-y-auto">
      {sections.map((section) => (
        <TestList
          key={section.stage}
          title={titleOf(section)}
          caption={t("firstFailure")}
          rows={section.rows.map(rowOf)}
        />
      ))}
    </div>
  );
}
