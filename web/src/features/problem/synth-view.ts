// What the tab «Синтез» shows of a check (FR-SYN-03, specs/08 §3): the synthesis stage, whose
// metrics (`synth/v1`) the cards compare (features/leaderboard/synth-cards.tsx), the check of the
// netlist that follows it in the same block, and the place. Of a stage checked at several parameter
// sets the metrics are those of the primary set, which rank; the extra sets are listed with the
// status of their check (ADR-0014, specs/08 §6).
import type { Check, Stage } from "@/features/submission/machine";
import { extraSetOf, type ParamSet } from "@/features/submission/param-sets";
import type { Schemas } from "@/lib/api/client";

import { blockOf, isNetlist, pendingStage } from "./pipeline-view";

/** The synthesis stage of a check at the primary set; undefined until it starts. */
export function synthStageOf(check: Check): Stage | undefined {
  return check.stages.find((stage) => stage.type === "synth" && extraSetOf(stage) === null);
}

/** The check of the netlist after synthesis at the primary set. */
export function netlistStageOf(check: Check): Stage | undefined {
  return check.stages.find((stage) => isNetlist(stage) && extraSetOf(stage) === null);
}

/** The check has the synth block: its tab is shown. */
export function hasSynth(pipeline: Schemas["PipelineInfo"], check: Check): boolean {
  return [...pipeline[check.kind], ...check.stages].some((stage) => blockOf(stage) === "synth");
}

/** How the synth block went at an extra set: its synthesis, then the check of its netlist. */
export interface SetCheck {
  set: ParamSet;
  status: "pending" | "running" | "passed" | "failed" | "notRun" | "error";
  /** The stage that decided a failure, or that runs: what the row tells about. */
  stage: Stage | null;
}

/** The extra sets of the synth block in the order of the pipeline, those not started yet too. */
export function setChecks(check: Check, pipeline: Schemas["PipelineInfo"]): SetCheck[] {
  const bySet = new Map<string, { set: ParamSet; stages: Stage[] }>();
  pipeline[check.kind].forEach(({ key, type, param_set }, ordinal) => {
    const set = extraSetOf({ param_set });
    if (set === null || blockOf({ key, type }) !== "synth") return;
    const stage =
      check.stages.find((item) => item.key === key) ?? pendingStage(key, type, ordinal, set);
    const entry = bySet.get(set.id) ?? { set, stages: [] };
    entry.stages.push(stage);
    bySet.set(set.id, entry);
  });
  return [...bySet.values()].map(({ set, stages }) => fold(check, set, stages));
}

function fold(check: Check, set: ParamSet, stages: readonly Stage[]): SetCheck {
  const decisive = stages.find((stage) => stage.status !== "passed" && stage.status !== "warning");
  if (decisive === undefined) return { set, status: "passed", stage: null };
  switch (decisive.status) {
    case "pending":
      if (check.done) return { set, status: "notRun", stage: null };
      // Synthesis passed, the check of its netlist is next.
      if (decisive !== stages[0]) return { set, status: "running", stage: decisive };
      return { set, status: "pending", stage: null };
    case "running":
      return { set, status: "running", stage: decisive };
    case "failed":
      return { set, status: "failed", stage: decisive };
    case "error":
      return { set, status: "error", stage: decisive };
    default:
      return { set, status: "notRun", stage: null };
  }
}

/** The filled part of the bar of the place, from the first place on the left: at least a sliver. */
export function placeShare({ rank, total }: Schemas["LeaderboardPlacement"]): number {
  return Math.min(1, Math.max(rank / total, 0.01));
}
