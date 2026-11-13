// What the results panel shows of a check (FR-RUN-04/05, specs/08 §3): its stages folded into the
// four pipeline blocks, and the facts the banners tell. precheck is shown in the lint block and
// netlist_sim in the synth block (specs/08 §6); blocks without stages are not shown (FR-RUN-02).
// A stage checked at several parameter sets runs as one instance per set, `<key>@<set>` (ADR-0014):
// its instances are drawn in the block of the stage.
import {
  PIPELINE_BLOCKS,
  type PipelineBlock,
  type StageStatus,
} from "@/components/domain/pipeline";
import { isSolutionFile } from "@/features/editor/languages";
import type { Check, Stage } from "@/features/submission/machine";
import {
  extraSetOf,
  type ParamSet,
  PRIMARY_SET,
  stageKeyOf,
} from "@/features/submission/param-sets";
import type { Schemas } from "@/lib/api/client";

export type Limit = NonNullable<Stage["limit"]>;

// By stage type; netlist_sim is a stage of type sim, known by its key (specs/06 §2).
const BLOCKS: Record<string, PipelineBlock> = {
  precheck: "lint",
  lint: "lint",
  sim: "sim",
  synth: "synth",
  formal: "formal",
};
const BLOCKS_BY_KEY: Record<string, PipelineBlock> = { netlist_sim: "synth" };

/** The block a stage is drawn in; undefined for a stage the panel does not show. */
export function blockOf(stage: { key: string; type: string }): PipelineBlock | undefined {
  return BLOCKS_BY_KEY[stageKeyOf(stage.key)] ?? BLOCKS[stage.type];
}

/** The check of the netlist after synthesis, at any set. */
export const isNetlist = (stage: { key: string }) => stageKeyOf(stage.key) in BLOCKS_BY_KEY;

/** The test group that Run checks; the others are hidden (specs/06 §3.4). */
export const OPEN_GROUP = "public";

/** The caption of a block in place of its status word. */
export type BlockDetail =
  /** The stage's own caption from the judge: "пройдено 4 из 4"; of a passed block, that of the
   * primary set, and `sets`: how many sets the block checked, when more than one. */
  | { kind: "caption"; text: string; sets?: number }
  | { kind: "warnings"; count: number }
  | { kind: "limit"; limit: Limit }
  /** A stage the check never reached. */
  | { kind: "notRun" }
  /** The check of the netlist runs or failed in the synth block (specs/08 §6); `caption`: the
   * stage's own, for the hover. */
  | { kind: "netlist"; caption: string | null };

export interface BlockView {
  block: PipelineBlock;
  /** As drawn: a stage stopped by a limit is drawn as a warning (mock-up ResultStates). */
  status: StageStatus;
  detail: BlockDetail | null;
  /** The extra parameter set of the instance that decides the block: the one that runs, failed or
   * hit a limit (specs/08 §6). */
  set: ParamSet | null;
  /** The time of the block's stages; of a running block, the time so far. */
  durationMs: number | null;
}

/** A stage of the pipeline the check has not started. */
export function pendingStage(
  key: string,
  type: string,
  ordinal: number,
  param_set: ParamSet | null = null,
): Stage {
  return {
    key,
    type,
    ordinal,
    param_set,
    status: "pending",
    failure_kind: null,
    limit: null,
    error_code: null,
    started_at: null,
    duration_ms: null,
    metrics_schema: null,
    metrics: {},
    cached: false,
    summary: { diagnostics: [], tests: [] },
  };
}

/** The stages to draw: those of the check over the pipeline of its kind; before the first check,
 * the stages of Run and Submit together. */
function stagesOf(pipeline: Schemas["PipelineInfo"], check: Check | null): Stage[] {
  const planned = check === null ? [...pipeline.submit, ...pipeline.run] : pipeline[check.kind];
  const stages = new Map<string, Stage>();
  planned.forEach(({ key, type, param_set }, ordinal) => {
    if (!stages.has(key)) stages.set(key, pendingStage(key, type, ordinal, param_set));
  });
  for (const stage of check?.stages ?? []) stages.set(stage.key, stage);
  return [...stages.values()].sort((a, b) => a.ordinal - b.ordinal);
}

/** The limit a stage hit: from its result, or from the verdict of a restored check. */
export function limitOf(stage: Stage, verdict: Check["verdict"]): Limit | null {
  if (stage.failure_kind !== "limit") return null;
  return (
    stage.limit ?? (verdict?.first_failure?.stage === stage.key ? verdict.limit : null) ?? null
  );
}

const countWarnings = (stages: readonly Stage[]) =>
  stages.reduce(
    (sum, stage) =>
      sum + stage.summary.diagnostics.filter((item) => item.severity === "warning").length,
    0,
  );

function foldBlock(
  block: PipelineBlock,
  stages: readonly Stage[],
  check: Check | null,
  runningMs: number | null,
): BlockView {
  const finished = check === null || check.done;
  const times = stages.flatMap((stage): number[] => {
    if (stage.status === "running") return runningMs === null ? [] : [runningMs];
    return stage.duration_ms == null ? [] : [stage.duration_ms];
  });
  const durationMs = times.length === 0 ? null : times.reduce((sum, ms) => sum + ms, 0);
  const caption = (stage: Stage | undefined): BlockDetail | null => {
    const text = stage?.summary.caption;
    return text ? { kind: "caption", text } : null;
  };

  // The first stage that did not pass decides: the instances of a stage run in a row and the first
  // failure skips the rest, so it is the worst of them. A block of passed stages shows the last
  // caption of its own stages at the primary set: the synth block shows the metrics of synthesis,
  // not the tests of the netlist, and those of the primary set, which rank (ADR-0014).
  const decisive = stages.find((stage) => stage.status !== "passed" && stage.status !== "warning");
  if (decisive === undefined) {
    const warnings = countWarnings(stages);
    const status = stages.some((stage) => stage.status === "warning") ? "warning" : "passed";
    const own = stages.findLast(
      (stage) => !isNetlist(stage) && extraSetOf(stage) === null && stage.summary.caption,
    );
    const sets = new Set(stages.map((stage) => stage.param_set?.id ?? PRIMARY_SET)).size;
    let detail = caption(own);
    if (status === "warning" && warnings > 0) detail = { kind: "warnings", count: warnings };
    else if (detail?.kind === "caption" && sets > 1) detail = { ...detail, sets };
    return { block, status, detail, set: null, durationMs };
  }
  const set = extraSetOf(decisive);
  const netlist: BlockDetail | null = isNetlist(decisive)
    ? { kind: "netlist", caption: decisive.summary.caption ?? null }
    : null;
  switch (decisive.status) {
    case "pending": {
      // Between two stages of the block, the block is still running: at the set that comes next.
      const started = decisive !== stages[0];
      if (started && !finished) {
        return { block, status: "running", detail: netlist, set, durationMs };
      }
      const detail = finished ? { kind: "notRun" as const } : null;
      return { block, status: "pending", detail, set: null, durationMs };
    }
    case "skipped": {
      const detail =
        decisive.summary.skip_reason === "cancelled" ? { kind: "notRun" as const } : null;
      return { block, status: "skipped", detail, set: null, durationMs: null };
    }
    case "failed": {
      const limit = limitOf(decisive, check?.verdict ?? null);
      if (limit !== null) {
        return { block, status: "warning", detail: { kind: "limit", limit }, set, durationMs };
      }
      return { block, status: "failed", detail: netlist ?? caption(decisive), set, durationMs };
    }
    case "error":
      return { block, status: "error", detail: null, set: null, durationMs: null };
    case "running":
      return { block, status: "running", detail: netlist ?? caption(decisive), set, durationMs };
    default:
      return { block, status: decisive.status, detail: caption(decisive), set: null, durationMs };
  }
}

/** The pipeline blocks of a check, or of the problem before its first check. */
export function pipelineView(
  pipeline: Schemas["PipelineInfo"],
  check: Check | null,
  runningMs: number | null,
): BlockView[] {
  const byBlock = new Map<PipelineBlock, Stage[]>();
  for (const stage of stagesOf(pipeline, check)) {
    const block = blockOf(stage);
    if (block === undefined) continue;
    byBlock.set(block, [...(byBlock.get(block) ?? []), stage]);
  }
  return PIPELINE_BLOCKS.flatMap((block) => {
    const stages = byBlock.get(block);
    return stages === undefined ? [] : [foldBlock(block, stages, check, runningMs)];
  });
}

/** The stage the verdict points at, or the first one that failed. */
export function failedStage(check: Check): Stage | null {
  const key = check.verdict?.first_failure?.stage;
  return (
    check.stages.find((stage) => stage.key === key) ??
    check.stages.find((stage) => stage.status === "failed" || stage.status === "error") ??
    null
  );
}

export type Failure =
  /** An open test: the first mismatch, if the testbench reported one. */
  | {
      kind: "test";
      name: string;
      cycle: number | null;
      mismatch: Schemas["Mismatch"] | null;
    }
  | { kind: "hidden"; index: number; total: number }
  /** No test to point at: the caption of the stage, if any. */
  | { kind: "other"; caption: string | null };

/** Why a check got `wrong_answer`. */
export function failureOf(check: Check): Failure {
  const stage = failedStage(check);
  if (stage === null) return { kind: "other", caption: null };
  const { tests, hidden_tests: hidden, caption } = stage.summary;
  const id = check.verdict?.first_failure?.test;
  const test =
    tests.find((item) => item.id === id) ?? tests.find((item) => item.status === "failed");
  if (test !== undefined) {
    const mismatch = test.mismatches[0] ?? null;
    return {
      kind: "test",
      name: test.name || test.id,
      cycle: mismatch?.cycle ?? test.cycle ?? null,
      mismatch,
    };
  }
  if (hidden?.failed_index != null) {
    return { kind: "hidden", index: hidden.failed_index, total: hidden.total };
  }
  return { kind: "other", caption: caption ?? null };
}

/** The first error of the failed stage: what a compile error or a forbidden construct shows. */
export function firstError(check: Check): Schemas["Diagnostic"] | null {
  const stage = failedStage(check);
  return stage?.summary.diagnostics.find((item) => item.severity === "error") ?? null;
}

/** Lint warnings of an accepted check. */
export function lintWarnings(check: Check): number {
  return countWarnings(check.stages.filter((stage) => blockOf(stage) === "lint"));
}

/** The diagnostics of precheck and lint on lines of the solution: the markers of the editor
 * (FR-EDT-05). */
export function editorDiagnostics(check: Check | null, language: string): Schemas["Diagnostic"][] {
  return (check?.stages ?? [])
    .filter((stage) => blockOf(stage) === "lint")
    .flatMap((stage) => stage.summary.diagnostics)
    .filter((item) => item.line != null && isSolutionFile(item.file ?? null, language));
}

/** "Test N of M" of a running simulation: the tests reported so far and how many there are. */
export function testProgress(
  check: Check,
  groups: Record<string, number>,
): { current: number; total: number } | null {
  const stage = check.stages.find((item) => item.status === "running");
  const current = stage?.summary.tests.length ?? 0;
  if (current === 0) return null;
  const total =
    check.kind === "run"
      ? (groups[OPEN_GROUP] ?? 0)
      : Object.values(groups).reduce((sum, count) => sum + count, 0);
  return total >= current ? { current, total } : null;
}
