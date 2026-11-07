"use client";

// A metric of synthesis (components.md, sheet CmpB): a label in capitals, the value in mono with
// its unit, the comparison with the reference in words and the reference numbers under it. Better
// than the reference: --ok with ↓; worse: --wn with ↑; as the reference: --mu. Without a comparison
// a note says why; a skeleton while the metric is not there; the explanation shows on hover and on
// focus (FR-SYN-03).
import { useTranslations } from "next-intl";
import type { ComponentProps } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type MetricComparison =
  /** `share`: the difference as a share of the reference; null when it cannot be one (a zero
   * reference). */
  { kind: "better" | "worse"; share: number | null } | { kind: "same" };

export interface MetricCardProps extends Omit<ComponentProps<"div">, "children"> {
  /** "Задержка пути": the card writes it in capitals. */
  label: string;
  /** Formatted: "0,84". Null: a skeleton. */
  value: string | null;
  /** "нс", "µm²": never in capitals. */
  unit?: string | undefined;
  /** After the unit: "≈ 1,19 ГГц". */
  extra?: string | undefined;
  /** Null: no comparison, `note` says why. */
  comparison?: MetricComparison | null | undefined;
  /** In place of the comparison: "сравнение появится после Submit". */
  note?: string | undefined;
  /** The reference numbers, formatted; a card without both shows a dash. */
  reference?: string | null | undefined;
  best?: string | null | undefined;
  /** What the metric means: on hover and on focus. */
  hint?: string | undefined;
}

const TONES = { better: "text-ok", worse: "text-wn", same: "text-mu" } as const;

function Comparison({ comparison }: { comparison: MetricComparison }) {
  const t = useTranslations("domain.metric");
  let text: string;
  if (comparison.kind === "same") {
    text = t("same");
  } else if (comparison.share === null) {
    text = t(comparison.kind);
  } else {
    // Whole percent, as the mock-up writes them; a difference that rounds to zero is still one.
    const percent = Math.round(comparison.share * 100);
    text = percent === 0 ? t(`${comparison.kind}Under`) : t(`${comparison.kind}By`, { percent });
  }
  return <span className={cn("text-caption font-medium", TONES[comparison.kind])}>{text}</span>;
}

export function MetricCard({
  label,
  value,
  unit,
  extra,
  comparison = null,
  note,
  reference = null,
  best = null,
  hint,
  className,
  ...props
}: MetricCardProps) {
  const t = useTranslations("domain.metric");
  const box = "flex min-w-0 flex-col gap-[3px] rounded-md border border-bd bg-sf px-3 py-2.5";
  if (value === null) {
    return (
      <div
        role="status"
        aria-label={t("loading", { label })}
        className={cn(box, "gap-1.5", className)}
        {...props}
      >
        <span className="font-mono text-label text-mu uppercase">{label}</span>
        <Skeleton className="h-[30px] w-[70%]" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-2.5 w-4/5" />
      </div>
    );
  }
  const numbers = [
    reference === null ? null : t("reference", { value: reference }),
    best === null ? null : t("best", { value: best }),
  ].filter((item) => item !== null);
  const card = (
    <div
      data-comparison={comparison?.kind ?? "none"}
      tabIndex={hint === undefined ? undefined : 0}
      className={cn(
        box,
        hint !== undefined && "outline-none focus-visible:ring-2 focus-visible:ring-ac",
        className,
      )}
      {...props}
    >
      <span className="font-mono text-label text-mu uppercase">{label}</span>
      <p className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
        <span className="font-mono text-metric">{value}</span>
        {(unit !== undefined || extra !== undefined) && (
          <span className="text-caption text-mu">
            {[unit, extra].filter((item) => item !== undefined).join(" · ")}
          </span>
        )}
      </p>
      {comparison === null ? (
        <span className="text-caption text-tx">{note ?? t("none")}</span>
      ) : (
        <Comparison comparison={comparison} />
      )}
      <span className="font-mono text-[11px] text-mu">
        {numbers.length === 0 ? "—" : numbers.join(" · ")}
      </span>
    </div>
  );
  return hint === undefined ? card : <Tooltip content={hint}>{card}</Tooltip>;
}
