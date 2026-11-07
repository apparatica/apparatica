"use client";

// The tab «Решения» of the problem page (FR-PRB-07, sheets LeftTabsA/B): the public solutions of
// every version — accepted Submits of signed-in users, the best one of an author and the others —
// in the order of the leaderboard, by another metric of its formula or the newest first. The code
// of others opens after the visitor's own accepted Submit of the problem (ОВ-2): until then the
// tab is a lock with the reason. The chevron of a row opens the solution page.
import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowRight, ChevronRight, FileX, Lock } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { profileHref } from "@/features/profile/href";
import { solutionHref } from "@/features/solution/href";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { getSolutions, leaderboardKeys } from "./api";
import { isMetricName, metricOf, useMetricWords } from "./metrics";
import { leaderboardHref } from "./query";

export const SOLUTIONS_PER_PAGE = 20;

export interface SolutionsTabProps {
  problem: Pick<Schemas["ProblemDetail"], "slug" | "version" | "leaderboard">;
  /** «Перейти к редактору» of the lock; without it there is no button (phones). */
  onEdit?: (() => void) | undefined;
}

/** The orders of the tab: the formula (the first metric is the order of places) and the newest. */
export function solutionSorts(order: readonly Schemas["LeaderboardKey"][]): string[] {
  const metrics = order.map(({ metric, dir }, index) =>
    index === 0 ? "rank" : dir === "asc" ? metric : `-${metric}`,
  );
  return [...(metrics.length > 0 ? metrics : ["rank"]), "-submitted_at"];
}

function Locked({ onEdit }: { onEdit?: (() => void) | undefined }) {
  const t = useTranslations("leaderboard.solutions");
  return (
    <div className="flex flex-col items-center gap-2.5 px-10 py-10 text-center">
      <div
        aria-hidden="true"
        className="mb-3 flex w-full max-w-[270px] flex-col gap-2 rounded-md border border-bd bg-ed p-4 blur-[1.5px]"
      >
        {[70, 92, 58, 84, 46, 76].map((width, index) => (
          <span key={index} className="h-2 rounded-sm bg-sf2" style={{ width: `${width}%` }} />
        ))}
      </div>
      <Lock size={22} aria-hidden="true" className="text-mu" />
      <h2 className="text-[14px] font-medium">{t("lockedTitle")}</h2>
      <p className="max-w-[340px] text-mu">{t("locked")}</p>
      <p className="max-w-[340px] text-caption text-mu">{t("lockedWhy")}</p>
      {onEdit !== undefined && (
        <Button variant="primary" onClick={onEdit} className="mt-1">
          {t("edit")}
        </Button>
      )}
    </div>
  );
}

export function SolutionsTab({ problem, onEdit }: SolutionsTabProps) {
  const t = useTranslations("leaderboard.solutions");
  const names = useTranslations("leaderboard");
  const words = useMetricWords();
  const order = problem.leaderboard?.order ?? [];
  const sorts = solutionSorts(order);
  const [sort, setSort] = useState(sorts[0] ?? "rank");
  const list = useInfiniteQuery({
    queryKey: leaderboardKeys.solutions(problem.slug, sort),
    queryFn: ({ pageParam }) =>
      getSolutions(problem.slug, { sort, page: pageParam, per_page: SOLUTIONS_PER_PAGE }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.per_page < last.total ? last.page + 1 : undefined,
  });

  const sortLabel = (value: string) => {
    if (value === "-submitted_at") return t("sort.newest");
    const key = value === "rank" ? order[0]?.metric : value.replace(/^-/, "");
    const name = key === undefined ? null : metricOf(key);
    if (name === null) return t("sort.rank");
    return isMetricName(name) ? names(`by.${name}`) : key;
  };

  if (list.isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-2 px-3.5 py-3">
        <Skeleton className="h-[30px] w-64" />
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    );
  }
  if (list.isError) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
        <p className="text-mu">{t("failed")}</p>
        <Button onClick={() => void list.refetch()}>{t("retry")}</Button>
      </div>
    );
  }
  const [first] = list.data.pages;
  const total = first?.total ?? 0;
  if (total === 0) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
        <FileX size={22} aria-hidden="true" className="text-mu" />
        <h2 className="text-[14px] font-medium">{t("emptyTitle")}</h2>
        <p className="max-w-[340px] text-mu">{t("empty")}</p>
      </div>
    );
  }
  if (first?.code_locked) return <Locked onEdit={onEdit} />;

  const items = list.data.pages.flatMap((page) => page.items);
  // The metrics of a row: the formula first, then the others; three fit in the line.
  const formula = order.map(({ metric }) => metric);
  const metricKeys = (metrics: Schemas["SolutionSummary"]["metrics"]) =>
    [
      ...formula,
      ...Object.keys(metrics)
        .sort()
        .filter((key) => !formula.includes(key)),
    ]
      .filter((key) => metrics[key] !== undefined)
      .slice(0, 3);
  return (
    <div className="flex flex-col">
      <div
        role="group"
        aria-label={t("sort.label")}
        className="flex flex-wrap gap-1.5 px-3.5 pt-3 pb-2"
      >
        {sorts.map((value) => (
          <Button
            key={value}
            variant={value === sort ? "outline" : "default"}
            aria-pressed={value === sort}
            onClick={() => setSort(value)}
          >
            {sortLabel(value)}
          </Button>
        ))}
      </div>
      <ul aria-label={t("label")} className="flex flex-col">
        {items.map((item) => {
          const metrics = metricKeys(item.metrics).map((key) =>
            words.inline(key, item.metrics[key] as number),
          );
          return (
            <li
              key={item.id}
              className="flex min-h-[52px] items-center gap-3 border-b border-bd px-3.5 py-2"
            >
              <span
                className={cn(
                  "w-6 flex-none text-right font-mono tabular-nums",
                  item.rank === null ? "text-mu" : item.rank <= 3 && "font-semibold",
                )}
              >
                {item.rank ?? "—"}
              </span>
              <Avatar name={item.author.nick} size={20} className="rounded-sm" />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="flex min-w-0 items-baseline gap-2">
                  <Link
                    href={profileHref(item.author.nick)}
                    className="truncate font-medium hover:text-ac hover:underline"
                  >
                    {item.author.nick}
                  </Link>
                  {item.version !== problem.version && (
                    <span className="flex-none font-mono text-label text-mu">
                      {t("version", { version: item.version })}
                    </span>
                  )}
                </span>
                {metrics.length > 0 && (
                  <span className="truncate font-mono text-caption text-mu">
                    {metrics.join(" · ")}
                  </span>
                )}
                {item.duplicate_of !== null && (
                  <span className="truncate text-caption text-mu">
                    {t("sameAs", { nick: item.duplicate_of.author.nick })}
                  </span>
                )}
              </div>
              <Link
                href={solutionHref(item.id)}
                aria-label={t("open", { nick: item.author.nick })}
                className="inline-flex size-6 flex-none items-center justify-center rounded-sm text-mu hover:bg-sf2 hover:text-tx max-sm:-mr-2.5 max-sm:size-11"
              >
                <ChevronRight size={14} aria-hidden="true" />
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-3 text-caption text-mu">
        <span>{t("shown", { shown: items.length, total })}</span>
        <span className="flex items-center gap-3">
          {list.hasNextPage && (
            <Button loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
              {t("more")}
            </Button>
          )}
          {problem.leaderboard !== null && (
            <Link
              href={leaderboardHref(problem.slug)}
              className="inline-flex items-center gap-1 text-ac underline"
            >
              {t("full")}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          )}
        </span>
      </div>
    </div>
  );
}
