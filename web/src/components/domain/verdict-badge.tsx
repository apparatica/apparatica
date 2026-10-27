// The status of a submission (components.md, sheet CmpA): 10 statuses, each with its own icon,
// so that the status never shows by the colour alone.
import {
  CircleCheck,
  CircleStop,
  CircleX,
  Clock,
  CodeXml,
  LoaderCircle,
  type LucideIcon,
  OctagonAlert,
  ShieldX,
  Timer,
  TriangleAlert,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentProps } from "react";

import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { useSeconds } from "./duration";
import type { PipelineBlock } from "./pipeline";

export type VerdictStatus = Schemas["Submission"]["status"];

const TONES = {
  ok: "bg-oks text-ok",
  er: "bg-ers text-er",
  wn: "bg-wns text-wn",
  in: "bg-ins text-in",
  neutral: "bg-sf2 text-tx inset-ring inset-ring-bc",
  // A platform failure differs by the shape: an outline without a fill.
  outline: "text-er inset-ring-[1.5px] inset-ring-er",
};

const STATUSES: Record<VerdictStatus, { icon: LucideIcon; tone: keyof typeof TONES }> = {
  accepted: { icon: CircleCheck, tone: "ok" },
  wrong_answer: { icon: CircleX, tone: "er" },
  compile_error: { icon: CodeXml, tone: "er" },
  accepted_with_warnings: { icon: TriangleAlert, tone: "wn" },
  limit_exceeded: { icon: Timer, tone: "wn" },
  forbidden_construct: { icon: ShieldX, tone: "er" },
  queued: { icon: Clock, tone: "in" },
  running: { icon: LoaderCircle, tone: "in" },
  cancelled: { icon: CircleStop, tone: "neutral" },
  internal_error: { icon: OctagonAlert, tone: "outline" },
};

export type VerdictBadgeProps = {
  status: VerdictStatus;
  /** queued: the place in the queue, "В очереди · позиция 3". */
  position?: number | null | undefined;
  /** running: the current block and its time, "Выполняется · синтез 4,2 с". */
  stage?: PipelineBlock | null | undefined;
  elapsedMs?: number | null | undefined;
  /** A 26 × 26 square with the icon only; the text goes to the title and the aria-label. */
  compact?: boolean;
} & Omit<ComponentProps<"span">, "children">;

export function VerdictBadge({
  status,
  position,
  stage,
  elapsedMs,
  compact = false,
  className,
  ...props
}: VerdictBadgeProps) {
  const t = useTranslations("domain");
  const seconds = useSeconds();
  const { icon: Icon, tone } = STATUSES[status];

  let label: string = t(`verdict.${status}`);
  if (status === "queued" && position != null) {
    label = t("verdict.queuedAt", { position });
  } else if (status === "running") {
    const detail = [
      stage == null ? null : t(`pipeline.current.${stage}`),
      elapsedMs == null ? null : seconds(elapsedMs),
    ]
      .filter(Boolean)
      .join(" ");
    if (detail !== "") label = `${label} · ${detail}`;
  }

  const icon = (
    <Icon
      aria-hidden="true"
      className={cn("size-3.5 flex-none", status === "running" && "animate-spin")}
    />
  );
  const base =
    "inline-flex h-[26px] items-center rounded-sm text-[12.5px] font-medium whitespace-nowrap";
  if (compact) {
    return (
      <span
        role="img"
        aria-label={label}
        title={label}
        data-status={status}
        className={cn(base, "w-[26px] justify-center", TONES[tone], className)}
        {...props}
      >
        {icon}
      </span>
    );
  }
  return (
    <span
      data-status={status}
      className={cn(base, "gap-[7px] px-2.5", TONES[tone], className)}
      {...props}
    >
      {icon}
      {label}
    </span>
  );
}
