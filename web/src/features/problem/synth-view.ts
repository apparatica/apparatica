// What the tab «Синтез» shows of a check (FR-SYN-03, specs/08 §3): the metrics of the synthesis
// stage (`synth/v1`) with the reference and the first place of the leaderboard, and the check of
// the netlist that follows it in the same block.
import type { MetricComparison } from "@/components/domain/metric-card";
import type { Check, Stage } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";

import { blockOf } from "./pipeline-view";

/** The metrics of the cards, in the order of the mock-up; all of them are better when lower. */
export const CARD_METRICS = ["critical_path_ns", "area_um2", "cells", "flops"] as const;
export type CardMetric = (typeof CARD_METRICS)[number];

export type Direction = Schemas["LeaderboardKey"]["dir"];

/** The synthesis stage of a check; undefined until it starts. */
export function synthStageOf(check: Check): Stage | undefined {
  return check.stages.find((stage) => stage.type === "synth");
}

/** The stages of the synth block after synthesis: the check of the netlist. */
export function netlistStageOf(check: Check): Stage | undefined {
  return check.stages.find((stage) => blockOf(stage) === "synth" && stage.type !== "synth");
}

/** The check has the synth block: its tab is shown. */
export function hasSynth(pipeline: Schemas["PipelineInfo"], check: Check): boolean {
  return [...pipeline[check.kind], ...check.stages].some((stage) => blockOf(stage) === "synth");
}

/** A number of `synth/v1`; undefined if the stage did not report it. */
export function metricOf(stage: Stage | undefined, metric: string): number | undefined {
  const value = stage?.metrics[metric];
  return typeof value === "number" ? value : undefined;
}

/** The direction of a metric: the formula tells it for its own metrics, the others are better
 * when lower. */
export function directionOf(
  key: string,
  formula: Schemas["LeaderboardFormula"] | null | undefined,
): Direction {
  return formula?.order.find((item) => item.metric === key)?.dir ?? "asc";
}

/** The value against the reference: better, worse or the same, and by what share of it. */
export function compareMetric(value: number, reference: number, dir: Direction): MetricComparison {
  if (value === reference) return { kind: "same" };
  const better = dir === "asc" ? value < reference : value > reference;
  return {
    kind: better ? "better" : "worse",
    share: reference === 0 ? null : Math.abs(value - reference) / Math.abs(reference),
  };
}

/** The filled part of the bar of the place, from the first place on the left: at least a sliver. */
export function placeShare({ rank, total }: Schemas["LeaderboardPlacement"]): number {
  return Math.min(1, Math.max(rank / total, 0.01));
}
