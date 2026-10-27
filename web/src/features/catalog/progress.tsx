"use client";

// The progress summary of the catalogue (FR-CAT-03): solved problems of every level out of all
// its problems. The solved ones come from the local history, so the server renders placeholders.
import { useTranslations } from "next-intl";

import { DifficultyBadge, difficultyTone } from "@/components/domain/difficulty-badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { History } from "@/features/guest/history";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { solvedByLevel } from "./view";

export function ProgressSummary({
  levels,
  progress,
  history,
}: {
  levels: Schemas["Difficulty"][];
  progress: Schemas["DifficultyTotal"][];
  history: History | null;
}) {
  const t = useTranslations("problems.progress");
  const solved = history === null ? null : solvedByLevel(history);
  return (
    <section
      aria-label={t("label")}
      className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-2"
    >
      {levels.map((level, index) => {
        const total = progress.find((item) => item.difficulty === level.key)?.total ?? 0;
        const done = Math.min(solved?.[level.key] ?? 0, total);
        return (
          <div
            key={level.key}
            className="flex flex-col gap-2 rounded-md border border-bd bg-sf px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <DifficultyBadge difficulty={level} rank={index + 1} />
              {solved === null ? (
                <Skeleton className="h-4 w-14" />
              ) : (
                <span className="font-mono text-caption text-mu">
                  {t.rich("solved", {
                    solved: done,
                    total,
                    n: (chunks) => <span className="font-medium text-tx">{chunks}</span>,
                  })}
                </span>
              )}
            </div>
            <div
              role="progressbar"
              aria-label={t("bar", { level: level.title, solved: done, total })}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={done}
              aria-busy={solved === null || undefined}
              className="h-1.5 rounded-md border border-bd bg-sf2"
            >
              <div
                className={cn("h-full rounded-md", difficultyTone(level.token), "bg-current")}
                style={{ width: total === 0 ? 0 : `${(done / total) * 100}%` }}
              />
            </div>
          </div>
        );
      })}
    </section>
  );
}
