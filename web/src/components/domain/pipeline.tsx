// The check pipeline (components.md, sheet CmpA): four blocks, each a PipelineStage with a title
// and a caption (time or reason). precheck is shown in the lint block, netlist_sim in the synth
// block (specs/08 §6); the caller maps the stages of a check onto the blocks.
import {
  CircleCheck,
  CircleMinus,
  CircleStop,
  CircleX,
  Clock,
  LoaderCircle,
  type LucideIcon,
  OctagonAlert,
  TriangleAlert,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentProps } from "react";

import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { useSeconds } from "./duration";

export const PIPELINE_BLOCKS = ["lint", "sim", "synth", "formal"] as const;
export type PipelineBlock = (typeof PIPELINE_BLOCKS)[number];
export type StageStatus = Schemas["StageResult"]["status"];

// The status shows by the icon, the frame and the caption, never by the colour alone.
const STAGES: Record<StageStatus, { icon: LucideIcon; className: string }> = {
  pending: { icon: Clock, className: "border border-bd text-mu" },
  running: { icon: LoaderCircle, className: "bg-ins text-in inset-ring inset-ring-in" },
  passed: { icon: CircleCheck, className: "bg-oks text-ok" },
  warning: { icon: TriangleAlert, className: "bg-wns text-wn" },
  failed: { icon: CircleX, className: "bg-ers text-er inset-ring inset-ring-er" },
  skipped: {
    icon: CircleMinus,
    className:
      "border border-dashed border-bd text-mu bg-[repeating-linear-gradient(135deg,transparent_0_6px,var(--sf2)_6px_8px)]",
  },
  cancelled: { icon: CircleStop, className: "border border-bc bg-sf2 text-mu" },
  // A platform failure: a frame without a fill, unlike a failed check.
  error: { icon: OctagonAlert, className: "border border-er text-er" },
};

export interface StageView {
  block: PipelineBlock;
  status: StageStatus;
  /** The reason or the result in place of the status word: "тест 7 из 32", "1 замечание". */
  detail?: string | undefined;
  /** The time of the stage; of a running stage, the time so far. */
  durationMs?: number | null | undefined;
}

export type PipelineStageProps = StageView & ComponentProps<"div">;

/** A block of the pipeline: icon, title, and the caption "<status or detail> · <time>". */
export function PipelineStage({
  block,
  status,
  detail,
  durationMs,
  className,
  ...props
}: PipelineStageProps) {
  const t = useTranslations("domain.pipeline");
  const seconds = useSeconds();
  const { icon: Icon, className: tone } = STAGES[status];
  const word = t(`status.${status}`);
  const caption = [detail ?? word, durationMs == null ? null : seconds(durationMs)]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      data-status={status}
      className={cn("flex h-11 min-w-0 items-center gap-2 rounded-sm px-2.5", tone, className)}
      {...props}
    >
      <Icon
        size={15}
        aria-hidden="true"
        className={cn("flex-none", status === "running" && "animate-spin")}
      />
      <div className="flex min-w-0 flex-col leading-[1.25]">
        <span className="truncate text-[12.5px] font-medium text-tx">{t(`blocks.${block}`)}</span>
        <span className="truncate font-mono text-[11px]">
          {detail !== undefined && <span className="sr-only">{word}: </span>}
          {caption}
        </span>
      </div>
    </div>
  );
}

/** Flex grow of the stages: the share of the total time. A stage that has not run gets none and
 * stays as wide as its text; without any times the room is shared equally. */
export function stageGrow(durations: readonly number[]): number[] {
  const total = durations.reduce((sum, ms) => sum + ms, 0);
  return durations.map((ms) => (total > 0 ? ms / total : 1));
}

export type PipelineProps = { stages: readonly StageView[] } & ComponentProps<"ol">;

/** The row of pipeline blocks: each as wide as its text, the room left goes by their times. */
export function Pipeline({ stages, className, ...props }: PipelineProps) {
  const t = useTranslations("domain.pipeline");
  const grow = stageGrow(stages.map((stage) => stage.durationMs ?? 0));
  return (
    <ol aria-label={t("label")} className={cn("flex gap-[3px]", className)} {...props}>
      {stages.map((stage, index) => (
        <li key={stage.block} className="flex min-w-0" style={{ flex: `${grow[index]} 1 auto` }}>
          <PipelineStage {...stage} className="flex-1" />
        </li>
      ))}
    </ol>
  );
}
