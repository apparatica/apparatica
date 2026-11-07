"use client";

// A public solution of a user, as the profile and the list of its solutions show it (mock-up
// Profile): the problem, the main metrics and the place in the leaderboard pages show now, the
// date; the row opens the solution page.
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { useShortDate } from "@/features/leaderboard/date";
import { METRIC_NAMES, metricOf, useMetricWords } from "@/features/leaderboard/metrics";
import { solutionHref } from "@/features/solution/href";
import type { Schemas } from "@/lib/api/client";

/** Metrics of a row: the named ones in their order (delay, area, …), two fit in the line. */
export function rowMetrics(metrics: Schemas["SolutionSummary"]["metrics"]): string[] {
  const rank = (key: string) => {
    const index = (METRIC_NAMES as readonly string[]).indexOf(metricOf(key));
    return index < 0 ? METRIC_NAMES.length : index;
  };
  return Object.keys(metrics)
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .slice(0, 2);
}

export function SolutionItem({ item }: { item: Schemas["SolutionSummary"] }) {
  const t = useTranslations("profile.solutions");
  const words = useMetricWords();
  const day = useShortDate();
  const details = [
    ...rowMetrics(item.metrics).map((key) => words.inline(key, item.metrics[key] as number)),
    ...(item.rank === null ? [] : [t("place", { rank: item.rank })]),
  ];
  return (
    <li className="border-t border-bd first:border-t-0">
      <Link
        href={solutionHref(item.id)}
        aria-label={t("open", { title: item.problem.title })}
        className="group flex items-center gap-2.5 py-2.5"
      >
        <ChevronRight
          size={14}
          aria-hidden="true"
          className="flex-none text-mu group-hover:text-tx"
        />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-medium group-hover:text-ac">{item.problem.title}</span>
          {details.length > 0 && (
            <span className="truncate font-mono text-caption text-mu">{details.join(" · ")}</span>
          )}
        </span>
        <time
          dateTime={item.submitted_at}
          className="flex-none text-right font-mono text-caption text-mu"
        >
          {day(item.submitted_at)}
        </time>
      </Link>
    </li>
  );
}
