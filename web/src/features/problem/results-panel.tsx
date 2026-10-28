"use client";

// The results panel of a problem page (specs/08 §3): the pipeline with the total time, the banner
// of the check and the result tabs under it, and before the first check a hint on Run and Submit
// (mock-up BenchEmpty). The tab of the waves comes in T1.17c.
import { SquareTerminal } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import { useSeconds } from "@/components/domain/duration";
import { Pipeline, type StageView } from "@/components/domain/pipeline";
import { Shortcut } from "@/components/ui/kbd";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type Check, isFinished, type Submission } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import type { Schemas } from "@/lib/api/client";

import { useNow } from "./clock";
import { type BlockDetail, type BlockView, pipelineView } from "./pipeline-view";
import { ResultBanner } from "./result-banner";
import { ResultsConsole } from "./results-console";
import { ResultsTests, TestsCounter } from "./results-tests";
import { ResultsSkeleton } from "./skeletons";
import { RUN_KEYS, SUBMIT_KEYS } from "./shortcuts";
import { testsCount, testsView } from "./tests-view";

const strong = (chunks: ReactNode) => <strong className="font-medium text-tx">{chunks}</strong>;

// The running time ticks by tenths; the countdown of a reconnect by seconds.
const RUNNING_TICK_MS = 100;
const WAITING_TICK_MS = 250;

type ResultsTab = "console" | "tests";

export type ResultsProblem = Pick<Schemas["ProblemDetail"], "pipeline" | "tests" | "language">;

export interface ResultsPanelProps {
  submission: SubmissionState;
  problem: ResultsProblem;
  /** A check is being created or runs. */
  busy: boolean;
  onCheck: (kind: Submission["kind"]) => void;
  onReveal: (line: number, column: number) => void;
}

function tickOf({ check, connection }: SubmissionState): number | null {
  if (connection?.state === "waiting") return WAITING_TICK_MS;
  return check?.runningSince == null ? null : RUNNING_TICK_MS;
}

function useDetail(): (detail: BlockDetail | null) => string | undefined {
  const t = useTranslations("problem.results.stage");
  return (detail) => {
    switch (detail?.kind) {
      case undefined:
        return undefined;
      case "caption":
        return detail.text;
      case "warnings":
        return t("warnings", { count: detail.count });
      case "limit":
        return t(`limit.${detail.limit}`);
      case "notRun":
        return t("notRun");
    }
  };
}

/** The caption right of the pipeline title: the wait, the time so far or the total. */
function PipelineTotal({ check, blocks }: { check: Check | null; blocks: BlockView[] }) {
  const t = useTranslations("problem.results.total");
  const seconds = useSeconds();
  if (check === null) return t("none");
  if (check.status === "queued")
    return check.queue?.etaS == null ? null : t("queued", { eta: check.queue.etaS });
  const time = seconds(blocks.reduce((sum, block) => sum + (block.durationMs ?? 0), 0));
  if (!isFinished(check)) return t("running", { time });
  if (check.status === "cancelled") return t("cancelled", { time });
  if (check.status === "internal_error") return t("interrupted", { time });
  return t("done", { time });
}

export function ResultsPanel({ submission, problem, busy, onCheck, onReveal }: ResultsPanelProps) {
  const t = useTranslations("problem.results");
  const tp = useTranslations("domain.pipeline");
  const tv = useTranslations("domain.verdict");
  const detailOf = useDetail();
  const now = useNow(tickOf(submission));
  // The console is open at first (specs/08 §3); the chosen tab stays for the next checks.
  const [tab, setTab] = useState<ResultsTab>("console");
  const { check } = submission;

  if (check === null && submission.restoring) {
    return (
      <section aria-label={t("label")} className="flex h-full min-h-0 flex-col bg-sf">
        <ResultsSkeleton />
      </section>
    );
  }

  const runningMs = check?.runningSince == null ? null : Math.max(0, now - check.runningSince);
  const blocks = pipelineView(problem.pipeline, check, runningMs);
  const stages: StageView[] = blocks.map(({ block, status, detail, durationMs }) => ({
    block,
    status,
    detail: detailOf(detail),
    durationMs,
    title: detail?.kind === "caption" ? detail.text : undefined,
  }));
  const tests = check === null ? [] : testsView(check, problem);
  const count = testsCount(tests);
  return (
    <section aria-label={t("label")} className="flex h-full min-h-0 flex-col bg-sf">
      <div className="flex flex-none flex-col gap-2.5 px-3.5 pt-3 pb-3.5">
        <div className="flex items-baseline justify-between gap-3 font-mono text-label text-mu uppercase">
          <h2>{tp("label")}</h2>
          <span className="normal-case">
            <PipelineTotal check={check} blocks={blocks} />
          </span>
        </div>
        <Pipeline stages={stages} />
        {check !== null && (
          <ResultBanner
            check={check}
            submission={submission}
            problem={problem}
            blocks={blocks}
            now={now}
            busy={busy}
            onCheck={onCheck}
            onReveal={onReveal}
          />
        )}
        <p aria-live="polite" className="sr-only">
          {check !== null && t("announce", { status: tv(check.status) })}
        </p>
      </div>
      {check !== null && (
        <Tabs
          value={tests.length === 0 ? "console" : tab}
          onValueChange={(value) => setTab(value as ResultsTab)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <TabsList aria-label={t("tabs.label")} className="flex-none px-3.5">
            <TabsTrigger value="console">{t("tabs.console")}</TabsTrigger>
            {tests.length > 0 && (
              <TabsTrigger value="tests">
                {t("tabs.tests")}
                {count !== null && <TestsCounter count={count} />}
              </TabsTrigger>
            )}
          </TabsList>
          <TabsContent value="console" className="min-h-0 flex-1">
            <ResultsConsole
              check={check}
              connection={submission.connection}
              problem={problem}
              runningMs={runningMs}
              onReveal={onReveal}
            />
          </TabsContent>
          <TabsContent value="tests" className="min-h-0 flex-1">
            <ResultsTests check={check} sections={tests} />
          </TabsContent>
        </Tabs>
      )}
      {check === null && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2.5 border-t border-bd bg-ed px-10 text-center">
          <SquareTerminal size={22} className="text-mu" aria-hidden="true" />
          <h2 className="text-[14px] font-medium">{t("emptyTitle")}</h2>
          <p className="max-w-[420px] text-mu">{t.rich("emptyDescription", { b: strong })}</p>
          <p className="flex gap-4 text-caption text-mu">
            <span>
              <Shortcut keys={RUN_KEYS} /> {t("runShortcut")}
            </span>
            <span>
              <Shortcut keys={SUBMIT_KEYS} /> {t("submitShortcut")}
            </span>
          </p>
        </div>
      )}
    </section>
  );
}
