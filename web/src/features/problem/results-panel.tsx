"use client";

// The results panel of a problem page (specs/08 §3): the pipeline with the total time, the banner
// of the check and the result tabs under it, and before the first check a hint on Run and Submit
// (mock-up BenchEmpty). The viewer of the waves outlives the checks: it is made once and kept. The
// limits of the guest show here too: the counter of checks left, the wait when they are spent.
import { SquareTerminal } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import { useSeconds } from "@/components/domain/duration";
import { Pipeline, type StageView } from "@/components/domain/pipeline";
import { Shortcut } from "@/components/ui/kbd";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type Check, isFinished, type Submission } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import { Viewer } from "@/features/waveview/viewer";
import type { Schemas } from "@/lib/api/client";

import { useCountdown, useNow } from "./clock";
import { LimitNotice, QuotaCounter } from "./limit-panel";
import { checksSpentUntil, quotaWarning } from "./limits";
import { type BlockDetail, type BlockView, pipelineView } from "./pipeline-view";
import { ResultBanner } from "./result-banner";
import { ResultsConsole } from "./results-console";
import { ResultsTests, TestsCounter } from "./results-tests";
import { ResultsWaves } from "./results-waves";
import { ResultsSkeleton } from "./skeletons";
import { RUN_KEYS, SUBMIT_KEYS } from "./shortcuts";
import { testsCount, testsView } from "./tests-view";
import { tracedTest, wavesView } from "./waves-view";

const strong = (chunks: ReactNode) => <strong className="font-medium text-tx">{chunks}</strong>;

// The running time ticks by tenths; the countdown of a reconnect by seconds.
const RUNNING_TICK_MS = 100;
const WAITING_TICK_MS = 250;

type ResultsTab = "console" | "tests" | "waves";

export type ResultsProblem = Pick<
  Schemas["ProblemDetail"],
  "pipeline" | "tests" | "language" | "interface"
>;

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
  const [viewer] = useState(() => new Viewer());
  const { check } = submission;
  // A start refused by a spent quota: the panel waits with the guest, then reads the quota again.
  const spentLeft = useCountdown(
    checksSpentUntil(submission.error, submission.failedAt),
    submission.failedAt,
    submission.refreshQuota,
  );
  const warning = quotaWarning(submission.quota);
  // The frame of the viewer is made when a test fails or the tab opens, before the trace is read:
  // Surfer boots meanwhile. Then it stays.
  const [viewerWanted, setViewerWanted] = useState(false);
  const failed = check?.stages.some((stage) =>
    stage.summary.tests.some((test) => test.status === "failed"),
  );
  if (!viewerWanted && (tab === "waves" || failed === true)) setViewerWanted(true);

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
  const open = tests.length === 0 ? "console" : tab;
  // Only whether a trace exists: the size limit of the viewer does not matter here.
  const traced =
    check === null ? null : tracedTest(wavesView(check, submission.submission, Infinity));
  const showWaves = () => {
    setTab("waves");
    viewer.focus();
  };
  return (
    <section aria-label={t("label")} className="flex h-full min-h-0 flex-col bg-sf">
      <div className="flex flex-none flex-col gap-2.5 px-3.5 pt-3 pb-3.5">
        <div className="flex min-h-[22px] flex-wrap items-center gap-x-3 gap-y-1 font-mono text-label text-mu uppercase">
          <h2 className="flex-1 whitespace-nowrap">{tp("label")}</h2>
          {warning !== null && <QuotaCounter window={warning} />}
          <span className="whitespace-nowrap normal-case">
            <PipelineTotal check={check} blocks={blocks} />
          </span>
        </div>
        <Pipeline stages={stages} />
        {check !== null && spentLeft !== null && <LimitNotice left={spentLeft} layout="banner" />}
        {check !== null && spentLeft === null && (
          <ResultBanner
            check={check}
            submission={submission}
            problem={problem}
            blocks={blocks}
            now={now}
            busy={busy}
            onCheck={onCheck}
            onReveal={onReveal}
            onShowWaves={traced === null ? null : showWaves}
          />
        )}
        <p aria-live="polite" className="sr-only">
          {check !== null && t("announce", { status: tv(check.status) })}
        </p>
      </div>
      {check !== null && (
        <Tabs
          value={open}
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
            {tests.length > 0 && <TabsTrigger value="waves">{t("tabs.waves")}</TabsTrigger>}
          </TabsList>
          {/* The tabs over each other: a covered viewer keeps running (results-waves.tsx). */}
          <div className="relative isolate min-h-0 flex-1">
            <TabsContent value="console" className="absolute inset-0 z-10 bg-sf">
              <ResultsConsole
                check={check}
                connection={submission.connection}
                problem={problem}
                runningMs={runningMs}
                onReveal={onReveal}
              />
            </TabsContent>
            <TabsContent value="tests" className="absolute inset-0 z-10 bg-sf">
              <ResultsTests
                check={check}
                sections={tests}
                traced={traced}
                onShowWaves={showWaves}
              />
            </TabsContent>
            {/* Always mounted, under the open tab: the viewer keeps its frame and its file. */}
            <TabsContent
              value="waves"
              forceMount
              inert={open !== "waves"}
              aria-hidden={open !== "waves"}
              className="absolute inset-0 z-0 data-[state=active]:z-20"
            >
              <ResultsWaves
                check={check}
                submission={submission}
                ports={problem.interface.ports}
                viewer={viewer}
                wanted={viewerWanted}
              />
            </TabsContent>
          </div>
        </Tabs>
      )}
      {check === null && spentLeft !== null && (
        <div className="flex flex-1 flex-col items-center justify-center border-t border-bd bg-ed px-10">
          <LimitNotice left={spentLeft} layout="panel" />
        </div>
      )}
      {check === null && spentLeft === null && (
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
