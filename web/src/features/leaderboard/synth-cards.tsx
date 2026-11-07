"use client";

// The metrics of a synthesis as MetricCard (FR-SYN-03, mock-ups BenchAccepted and Solution): the
// delay with the frequency, the area, the cells and the flops of `synth/v1`, each compared with
// the reference in words and with the reference and the first place in numbers. The tab «Синтез»
// shows those of a check, the solution page those of a public solution.
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { MetricCard } from "@/components/domain/metric-card";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { CARD_METRICS, compareMetric, directionOf, useMetricWords } from "./metrics";

export type Metrics = Record<string, number>;

export interface SynthCardsProps {
  /** The key of the synthesis stage: the metrics of the reference and the best are
   * `<key>.<metric>`. */
  stage: string;
  /** `synth/v1` of the stage. */
  metrics: Record<string, unknown>;
  reference: Metrics | null;
  best: Metrics | null;
  /** The formula of the leaderboard: the direction of its metrics. */
  order: readonly Schemas["LeaderboardKey"][] | undefined;
  /** Why a card has no comparison with the reference. */
  note: string;
  className?: string;
}

const numberOf = (metrics: Record<string, unknown>, metric: string): number | undefined => {
  const value = metrics[metric];
  return typeof value === "number" ? value : undefined;
};

/** The grid of the cards: as many in a row as fit, at least 150 px each. */
export function CardGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div className={cn("grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2", className)}>
      {children}
    </div>
  );
}

export function SynthCards({
  stage,
  metrics,
  reference,
  best,
  order,
  note,
  className,
}: SynthCardsProps) {
  const t = useTranslations("leaderboard.synth");
  const format = useFormatter();
  const words = useMetricWords();

  const fmax = numberOf(metrics, "fmax_mhz");
  const frequency =
    fmax === undefined
      ? undefined
      : fmax >= 1000
        ? t("ghz", { value: format.number(fmax / 1000, { maximumFractionDigits: 2 }) })
        : t("mhz", { value: format.number(fmax, { maximumFractionDigits: 0 }) });

  return (
    <CardGrid className={className}>
      {CARD_METRICS.map((metric) => {
        const value = numberOf(metrics, metric);
        if (value === undefined) return null;
        const key = `${stage}.${metric}`;
        const theirs = reference?.[key];
        const top = best?.[key];
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
            comparison={
              theirs === undefined ? null : compareMetric(value, theirs, directionOf(key, order))
            }
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
