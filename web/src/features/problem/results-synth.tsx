"use client";

// The tab «Синтез» of the results (FR-SYN-03, mock-up BenchAccepted): the metrics of the synthesis
// as cards compared with the reference and the first place of the leaderboard, the check of the
// netlist under them, and the place the Submit took. The reference and the first place come from
// the leaderboard of the problem: one row of it carries both.
import { skipToken, useQuery } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleMinus,
  CircleX,
  Clock,
  LoaderCircle,
  type LucideIcon,
  OctagonAlert,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { MetricCard, type MetricComparison } from "@/components/domain/metric-card";
import { useGuest } from "@/features/account/session";
import { getLeaderboardTop, leaderboardKeys } from "@/features/leaderboard/api";
import { directionOf, useMetricWords, useOrderWords } from "@/features/leaderboard/metrics";
import { type Check, isFinished, type Stage } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import {
  CARD_METRICS,
  compareMetric,
  metricOf,
  netlistStageOf,
  placeShare,
  synthStageOf,
} from "./synth-view";

export type SynthProblem = Pick<Schemas["ProblemDetail"], "slug" | "leaderboard" | "reference">;

export interface ResultsSynthProps {
  check: Check;
  problem: SynthProblem;
}

export function ResultsSynth({ check, problem }: ResultsSynthProps) {
  const t = useTranslations("problem.results.synth");
  const synth = synthStageOf(check);
  const finished = isFinished(check);
  let body: ReactNode;
  if (synth === undefined || synth.status === "pending" || synth.status === "running") {
    body = finished ? (
      <SynthNotice title={t("notRun")}>{t("notRunBody")}</SynthNotice>
    ) : (
      <CardGrid>
        {CARD_METRICS.map((metric) => (
          <MetricCard key={metric} label={t(`metrics.${metric}`)} value={null} />
        ))}
      </CardGrid>
    );
  } else if (synth.status === "failed") {
    body = (
      <SynthNotice title={t("failed")} tone="er" icon={CircleX}>
        {synth.summary.caption ? `${synth.summary.caption}. ` : null}
        {t("failedBody")}
      </SynthNotice>
    );
  } else if (synth.status === "error") {
    body = (
      <SynthNotice title={t("error")} tone="er" icon={OctagonAlert}>
        {t("errorBody")}
      </SynthNotice>
    );
  } else if (synth.status === "skipped" || synth.status === "cancelled") {
    body = <SynthNotice title={t("notRun")}>{t("notRunBody")}</SynthNotice>;
  } else {
    body = (
      <>
        <SynthCards synth={synth} problem={problem} />
        <NetlistRow stage={netlistStageOf(check)} finished={finished} />
        <Place check={check} problem={problem} />
      </>
    );
  }
  return (
    <section
      aria-label={t("label")}
      className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto border-t border-bd bg-ed px-3.5 py-3"
    >
      {body}
    </section>
  );
}

function CardGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">{children}</div>
  );
}

function SynthCards({ synth, problem }: { synth: Stage; problem: SynthProblem }) {
  const t = useTranslations("problem.results.synth");
  const format = useFormatter();
  const words = useMetricWords();
  const ranked = problem.leaderboard !== null;
  const board = useQuery({
    queryKey: leaderboardKeys.top(problem.slug),
    queryFn: ranked ? () => getLeaderboardTop(problem.slug) : skipToken,
  });
  const reference = board.data?.reference?.metrics ?? null;
  const best = board.data?.best?.metrics ?? null;
  let note: string;
  if (!ranked) note = t("note.noBoard");
  else if (board.isPending) note = t("note.loading");
  else if (board.isError) note = t("note.failed");
  else note = problem.reference === null ? t("note.noReference") : t("note.unmeasured");

  const fmax = metricOf(synth, "fmax_mhz");
  const frequency =
    fmax === undefined
      ? undefined
      : fmax >= 1000
        ? t("ghz", { value: format.number(fmax / 1000, { maximumFractionDigits: 2 }) })
        : t("mhz", { value: format.number(fmax, { maximumFractionDigits: 0 }) });

  return (
    <CardGrid>
      {CARD_METRICS.map((metric) => {
        const value = metricOf(synth, metric);
        if (value === undefined) return null;
        const key = `${synth.key}.${metric}`;
        const theirs = reference?.[key];
        const top = best?.[key];
        const comparison: MetricComparison | null =
          theirs === undefined
            ? null
            : compareMetric(value, theirs, directionOf(key, problem.leaderboard?.order));
        return (
          <MetricCard
            key={metric}
            label={t(`metrics.${metric}`)}
            value={words.value(key, value)}
            unit={
              metric === "critical_path_ns" || metric === "area_um2"
                ? t(`units.${metric}`)
                : undefined
            }
            extra={metric === "critical_path_ns" ? frequency : undefined}
            comparison={comparison}
            note={note}
            reference={theirs === undefined ? null : words.value(key, theirs)}
            best={top === undefined ? null : words.value(key, top)}
            hint={t(`hints.${metric}`)}
          />
        );
      })}
    </CardGrid>
  );
}

const TONES = { ok: "text-ok", in: "text-in", er: "text-er", mu: "text-mu" } as const;

function NetlistRow({ stage, finished }: { stage: Stage | undefined; finished: boolean }) {
  const t = useTranslations("problem.results.synth.netlist");
  if (stage === undefined && finished) return null;
  let icon: LucideIcon = Clock;
  let tone: keyof typeof TONES = "mu";
  let text = t("pending");
  let hint: string | null = null;
  switch (stage?.status) {
    case undefined:
    case "pending":
      if (finished) {
        icon = CircleMinus;
        text = t("notRun");
      }
      break;
    case "running":
      icon = LoaderCircle;
      tone = "in";
      text = t("running");
      break;
    case "passed":
    case "warning":
      icon = CircleCheck;
      tone = "ok";
      text = stage.summary.caption
        ? t("passed", { caption: stage.summary.caption })
        : t("passedPlain");
      break;
    case "failed":
      icon = CircleX;
      tone = "er";
      text = stage.summary.caption || t("failed");
      hint = stage.summary.diagnostics.find((item) => item.severity === "info")?.message ?? null;
      break;
    case "skipped":
    case "cancelled":
      icon = CircleMinus;
      text = t("notRun");
      break;
    case "error":
      icon = OctagonAlert;
      tone = "er";
      text = t("error");
      break;
  }
  const Icon = icon;
  return (
    <div
      data-status={stage?.status ?? "pending"}
      className="flex items-start gap-2.5 rounded-md border border-bd bg-sf px-3 py-2"
    >
      <Icon
        size={14}
        aria-hidden="true"
        className={cn("mt-[3px] flex-none", TONES[tone], icon === LoaderCircle && "animate-spin")}
      />
      <div className="min-w-0">
        <p className="font-medium">{t("title")}</p>
        <p className={cn("text-caption", tone === "er" ? "text-er" : "text-mu")}>{text}</p>
        {hint !== null && <p className="text-caption text-tx">{hint}</p>}
      </div>
    </div>
  );
}

function Place({ check, problem }: ResultsSynthProps) {
  const t = useTranslations("problem.results.synth.place");
  const { names: order } = useOrderWords(problem.leaderboard?.order ?? []);
  const guest = useGuest();
  const { placement } = check;
  if (problem.leaderboard === null || !isFinished(check)) return null;
  if (placement === null) {
    const accepted = check.status === "accepted" || check.status === "accepted_with_warnings";
    return guest && accepted ? <p className="text-caption text-mu">{t("guest")}</p> : null;
  }
  const { rank, total } = placement;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="font-mono text-label text-mu uppercase">{t("title", { order })}</h3>
        <span className="font-mono text-caption">
          <span className="font-medium text-ok">{rank}</span>{" "}
          <span className="text-mu">{t("of", { total })}</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={t("title", { order })}
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={rank}
        aria-valuetext={`${rank} ${t("of", { total })}`}
        className="relative h-1.5 rounded-sm border border-bd bg-sf2"
      >
        <div
          className="absolute -inset-y-px left-0 rounded-sm bg-ok"
          style={{ width: `${placeShare(placement) * 100}%` }}
        />
      </div>
      <div className="flex justify-between gap-3 font-mono text-label text-mu">
        <span>1</span>
        <span>
          {total === 1
            ? t("alone")
            : t("betterThan", { percent: Math.round(placement.better_than * 100) })}
        </span>
        <span>{total}</span>
      </div>
      {!placement.is_best && <p className="text-caption text-mu">{t("earlier")}</p>}
      {placement.is_best && placement.duplicate_of !== null && (
        <p className="text-caption text-mu">{t("duplicate")}</p>
      )}
    </div>
  );
}

function SynthNotice({
  title,
  tone = "mu",
  icon: Icon = CircleMinus,
  children,
}: {
  title: string;
  tone?: "mu" | "er";
  icon?: LucideIcon;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-10 text-center">
      <Icon size={22} aria-hidden="true" className={TONES[tone]} />
      <h3 className="text-[14px] font-medium">{title}</h3>
      <p className="max-w-[420px] text-mu">{children}</p>
    </div>
  );
}
