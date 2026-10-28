"use client";

// The banner under the pipeline (FR-RUN-05, specs/08 §3, mock-ups Bench*, ResultStates): what
// the check came to, why, and what to do next. The verdict shows after `finalized` only; a lost
// stream of a check that is not finished takes the place of the banner.
import {
  CircleCheck,
  CircleStop,
  CircleX,
  Clock,
  Download,
  LoaderCircle,
  type LucideIcon,
  OctagonAlert,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { useSeconds } from "@/components/domain/duration";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { isSolutionFile } from "@/features/editor/languages";
import { type Check, isFinished, type Submission } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import { apiUrl } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import {
  type BlockView,
  failedStage,
  failureOf,
  firstError,
  limitOf,
  lintWarnings,
  testProgress,
} from "./pipeline-view";

type Tone = "in" | "ok" | "wn" | "er" | "neutral";

const TONES: Record<Tone, { box: string; text: string }> = {
  in: { box: "bg-ins", text: "text-in" },
  ok: { box: "bg-oks", text: "text-ok" },
  wn: { box: "bg-wns", text: "text-wn" },
  er: { box: "bg-ers", text: "text-er" },
  neutral: { box: "border border-bc bg-sf2", text: "text-tx" },
};

export interface BannerProps {
  tone: Tone;
  icon: LucideIcon;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  spin?: boolean;
}

/** A tinted box: icon, title in the colour of the tone, explanation, actions on the right. */
export function Banner({ tone, icon: Icon, title, children, actions, spin = false }: BannerProps) {
  const { box, text } = TONES[tone];
  return (
    <div
      data-tone={tone}
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md px-3.5 py-3", box)}
    >
      <Icon
        size={18}
        aria-hidden="true"
        className={cn("flex-none self-start", text, spin && "animate-spin")}
      />
      <div className="min-w-0 flex-[1_1_260px]">
        <p className={cn("font-medium", text)}>{title}</p>
        {children !== undefined && <div className="text-tx">{children}</div>}
      </div>
      {actions !== undefined && <div className="flex flex-none flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const code = (chunks: ReactNode) => (
  <code className="rounded-xs border border-bd bg-sf2 px-1 font-mono text-[12px]">{chunks}</code>
);

export interface ResultBannerProps {
  check: Check;
  submission: SubmissionState;
  problem: Pick<Schemas["ProblemDetail"], "tests" | "language">;
  /** The pipeline as drawn: the running block and its time. */
  blocks: readonly BlockView[];
  /** `Date.now()` of the last tick: the countdown to the next reconnect. */
  now: number;
  /** A check is being created or runs: Retry and Submit wait. */
  busy: boolean;
  onCheck: (kind: Submission["kind"]) => void;
  /** Puts the cursor of the editor on a line of the solution. */
  onReveal: (line: number, column: number) => void;
}

export function ResultBanner(props: ResultBannerProps) {
  const { check, submission } = props;
  const { connection } = submission;
  if (!isFinished(check) && connection !== null) {
    if (connection.state === "failed" && connection.error !== null) return <GoneBanner />;
    const lost =
      connection.state === "waiting" ||
      connection.state === "failed" ||
      (connection.state === "connecting" && connection.lostAt !== null);
    if (lost) return <LostBanner {...props} />;
  }
  switch (check.status) {
    case "queued":
      return <QueuedBanner {...props} />;
    case "running":
      return <RunningBanner {...props} />;
    case "accepted":
    case "accepted_with_warnings":
      return <AcceptedBanner {...props} />;
    case "wrong_answer":
      return <WrongBanner {...props} />;
    case "compile_error":
    case "forbidden_construct":
      return <CompileBanner {...props} />;
    case "limit_exceeded":
      return <LimitBanner {...props} />;
    case "cancelled":
      return <CancelledBanner {...props} />;
    case "internal_error":
      return <InternalBanner {...props} />;
  }
}

function CancelButton({ submission }: { submission: SubmissionState }) {
  const t = useTranslations("problem.results");
  return (
    <Button loading={submission.cancelling} onClick={submission.cancel}>
      {t("cancel")}
    </Button>
  );
}

function QueuedBanner({ check, submission }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const { queue } = check;
  return (
    <Banner
      tone="in"
      icon={Clock}
      title={queue === null ? t("queued") : t("queuedAt", { position: queue.position })}
      actions={<CancelButton submission={submission} />}
    >
      {queue?.etaS == null ? t("queuedNoEta") : t("queuedEta", { eta: queue.etaS })}
    </Banner>
  );
}

function RunningBanner({ check, submission, problem, blocks }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const tp = useTranslations("domain.pipeline");
  const seconds = useSeconds();
  // The block, not the stage: its time is the one the pipeline shows.
  const running = blocks.find((block) => block.status === "running");
  let title = t("running");
  if (running !== undefined) {
    const name = tp(`current.${running.block}`);
    title =
      running.durationMs === null
        ? t("runningStage", { stage: name })
        : t("runningStageTime", { stage: name, time: seconds(running.durationMs) });
  }
  const progress = testProgress(check, problem.tests);
  const note = check.heartbeat?.note;
  return (
    <Banner
      tone="in"
      icon={LoaderCircle}
      spin
      title={title}
      actions={<CancelButton submission={submission} />}
    >
      {note && <>{note} </>}
      {progress !== null && <>{t("runningTests", progress)} </>}
      {t("runningBody")}
    </Banner>
  );
}

function AcceptedBanner({ check, busy, onCheck }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const format = useFormatter();
  const lint = lintWarnings(check);
  const warned = check.status === "accepted_with_warnings";
  if (check.kind === "run") {
    return (
      <Banner
        tone="ok"
        icon={CircleCheck}
        title={warned && lint > 0 ? t("runPassedLint", { count: lint }) : t("runPassed")}
        actions={
          <Button variant="primary" disabled={busy} onClick={() => onCheck("submit")}>
            {t("submit")}
          </Button>
        }
      >
        {t("runPassedBody")}
      </Banner>
    );
  }
  if (!warned) {
    return (
      <Banner tone="ok" icon={CircleCheck} title={t("accepted")}>
        {t("acceptedBody")}
      </Banner>
    );
  }
  const sources = (check.verdict?.warnings ?? []).filter(
    (source): source is "lint" | "formal" => source === "lint" || source === "formal",
  );
  if (lint > 0 && sources.every((source) => source === "lint")) {
    return (
      <Banner tone="ok" icon={CircleCheck} title={t("acceptedLint", { count: lint })}>
        {t("acceptedLintBody")}
      </Banner>
    );
  }
  const named = sources.map((source) => t(`sources.${source}`));
  return (
    <Banner tone="ok" icon={CircleCheck} title={t("acceptedNotes")}>
      {named.length > 0 && t("acceptedNotesBody", { sources: format.list(named) })}
    </Banner>
  );
}

function WrongBanner({ check }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const failure = failureOf(check);
  let body: ReactNode;
  if (failure.kind === "test") {
    const { name, cycle, mismatch } = failure;
    if (mismatch !== null) {
      const { signal, expected, actual, hint } = mismatch;
      body = t.rich("wrongMismatch", {
        name,
        cycle: mismatch.cycle,
        signal,
        expected,
        actual,
        code,
      });
      if (hint) {
        body = (
          <>
            {body} {t("wrongHint", { hint: hint.replace(/[.\s]+$/, "") })}
          </>
        );
      }
    } else {
      body = cycle === null ? t("wrongTest", { name }) : t("wrongCycle", { name, cycle });
    }
  } else if (failure.kind === "hidden") {
    body = t("wrongHidden", { index: failure.index, total: failure.total });
  } else {
    body =
      failure.caption === null ? t("wrongOther") : t("wrongCaption", { caption: failure.caption });
  }
  return (
    <Banner
      tone="er"
      icon={CircleX}
      title={check.kind === "run" ? t("wrongRun") : t("wrongSubmit")}
    >
      {body}
    </Banner>
  );
}

function CompileBanner({ check, problem, onReveal }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const forbidden = check.status === "forbidden_construct";
  const error = firstError(check);
  let body: ReactNode;
  if (error !== null && error.line != null) {
    const { line, col, message, file } = error;
    body = t.rich("diagnosticAt", {
      line,
      message,
      link: (chunks) =>
        isSolutionFile(file ?? null, problem.language) ? (
          <button
            type="button"
            className="cursor-pointer text-ac underline underline-offset-2"
            onClick={() => onReveal(line, col ?? 1)}
          >
            {chunks}
          </button>
        ) : (
          chunks
        ),
    });
  } else if (error !== null) {
    body = error.message;
  } else {
    const caption = failedStage(check)?.summary.caption;
    if (forbidden) body = t("forbiddenOther");
    else body = caption ? t("compileCaption", { caption }) : t("compileOther");
  }
  return (
    <Banner tone="er" icon={CircleX} title={forbidden ? t("forbidden") : t("compile")}>
      {body}
    </Banner>
  );
}

function LimitBanner({ check, submission }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const format = useFormatter();
  const stage = failedStage(check);
  const limit = (stage === null ? null : limitOf(stage, check.verdict)) ?? check.verdict?.limit;
  const key = limit ?? "other";
  let title = t(`limit.${key}`);
  const truncated = check.console.findLast((entry) => entry.kind === "truncated");
  if (limit === "output" && truncated?.kind === "truncated") {
    const kb = truncated.limitKb;
    const size =
      kb % 1024 === 0
        ? format.number(kb / 1024, { style: "unit", unit: "megabyte" })
        : format.number(kb, { style: "unit", unit: "kilobyte" });
    title = t("limitOf", { title, size });
  }
  const log = submission.submission?.artifacts.find(
    (artifact) =>
      artifact.kind === "log" && artifact.stage === stage?.key && artifact.state === "ready",
  );
  const href =
    log === undefined || stage === null
      ? null
      : apiUrl(
          `/api/v1/submissions/${encodeURIComponent(check.id)}/artifacts/log?stage=${encodeURIComponent(stage.key)}`,
        );
  return (
    <Banner
      tone="wn"
      icon={TriangleAlert}
      title={title}
      actions={
        limit === "output" && href !== null ? (
          <Button asChild>
            <a href={href} download>
              <Download aria-hidden="true" />
              {t("downloadLog")}
            </a>
          </Button>
        ) : undefined
      }
    >
      {t.rich(`advice.${key}`, { code })}
    </Banner>
  );
}

function CancelledBanner({ submission }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const elsewhere = !submission.cancelRequested;
  const showLatest = async () => {
    if (!(await submission.showLatest())) notify({ tone: "in", title: t("noLatest") });
  };
  return (
    <Banner
      tone="neutral"
      icon={CircleStop}
      title={t("cancelled")}
      actions={
        elsewhere ? (
          <Button variant="ghost" onClick={() => void showLatest()}>
            {t("showLatest")}
          </Button>
        ) : undefined
      }
    >
      {elsewhere ? t("cancelledElsewhere") : t("cancelledHere")}
    </Banner>
  );
}

function InternalBanner({ check, busy, onCheck }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const format = useFormatter();
  const codes = check.verdict?.error_codes ?? [];
  return (
    <Banner
      tone="er"
      icon={OctagonAlert}
      title={t("internal")}
      actions={
        <Button variant="primary" disabled={busy} onClick={() => onCheck(check.kind)}>
          {t("retry")}
        </Button>
      }
    >
      {t("internalBody")}
      {codes.length > 0 && (
        <> {t.rich("internalCode", { code, codes: format.list(codes, { type: "unit" }) })}</>
      )}
    </Banner>
  );
}

function LostBanner({ submission, now }: ResultBannerProps) {
  const t = useTranslations("problem.results.banner");
  const { connection } = submission;
  let title = t("lostConnecting");
  let body: ReactNode = t("lostBody");
  if (connection?.state === "waiting") {
    const seconds = Math.max(1, Math.ceil((connection.at - now) / 1000));
    title = t("lostRetry", { seconds });
    body = (
      <>
        {t("lostAttempt", connection)} {t("lostBody")}
      </>
    );
  } else if (connection?.state === "failed") {
    title = t("lost");
    body = t("lostFailed");
  }
  return (
    <Banner
      tone="wn"
      icon={WifiOff}
      title={title}
      actions={<Button onClick={submission.reconnect}>{t("connect")}</Button>}
    >
      {body}
    </Banner>
  );
}

function GoneBanner() {
  const t = useTranslations("problem.results.banner");
  return (
    <Banner tone="wn" icon={WifiOff} title={t("gone")}>
      {t("goneBody")}
    </Banner>
  );
}
