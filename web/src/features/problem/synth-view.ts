// What the tab «Синтез» shows of a check (FR-SYN-03, specs/08 §3): the synthesis stage, whose
// metrics (`synth/v1`) the cards compare (features/leaderboard/synth-cards.tsx), the check of the
// netlist that follows it in the same block, and the place.
import type { Check, Stage } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";

import { blockOf } from "./pipeline-view";

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

/** The filled part of the bar of the place, from the first place on the left: at least a sliver. */
export function placeShare({ rank, total }: Schemas["LeaderboardPlacement"]): number {
  return Math.min(1, Math.max(rank / total, 0.01));
}
