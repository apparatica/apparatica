"use client";

// The tab «Рейтинг» of the problem page (FR-PRB-07, sheet LeftTabsA): the top of the leaderboard
// by the main metric, the own row after a gap, or why there is none; the link to the full page.
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Info, Trophy } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import {
  type LeaderboardCell,
  LeaderboardGap,
  LeaderboardRow,
} from "@/components/domain/leaderboard-row";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useGuest } from "@/features/account/session";
import { useAuthorNames } from "@/features/profile/author";
import { solutionHref } from "@/features/solution/href";
import type { Schemas } from "@/lib/api/client";
import { loginHref } from "@/lib/session";

import { getLeaderboard, leaderboardKeys } from "./api";
import { useMetricWords } from "./metrics";
import { leaderboardHref } from "./query";

/** Rows of the short leaderboard, as in the mock-up. */
export const SHORT_ROWS = 5;

export function LeaderboardTab({ problem }: { problem: string }) {
  const t = useTranslations("leaderboard.tab");
  const words = useMetricWords();
  const authors = useAuthorNames();
  const guest = useGuest();
  const board = useQuery({
    queryKey: leaderboardKeys.short(problem),
    queryFn: () => getLeaderboard(problem, { per_page: SHORT_ROWS }),
  });
  const full = leaderboardHref(problem);
  const link = (chunks: ReactNode) => (
    <Link href={full} className="whitespace-nowrap text-ac underline">
      {chunks}
    </Link>
  );

  if (board.isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-2 px-3.5 py-3">
        <Skeleton className="h-3.5 w-40" />
        {Array.from({ length: SHORT_ROWS }, (_, index) => (
          <Skeleton key={index} className="h-[26px]" />
        ))}
      </div>
    );
  }
  if (board.isError) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
        <p className="text-mu">{t("failed")}</p>
        <Button onClick={() => void board.refetch()}>{t("retry")}</Button>
      </div>
    );
  }
  const { items, me, entries, order } = board.data;
  if (entries === 0) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
        <Trophy size={22} aria-hidden="true" className="text-mu" />
        <h2 className="text-[14px] font-medium">{t("emptyTitle")}</h2>
        <p className="max-w-[340px] text-mu">{t("empty")}</p>
      </div>
    );
  }
  const primary = order[0]?.metric;
  const cells = (row: Schemas["LeaderboardRow"]): LeaderboardCell[] => {
    if (primary === undefined) return [];
    const value = row.metrics[primary];
    return [
      {
        key: primary,
        text: value === undefined ? "—" : words.value(primary, value),
        unit: words.unit(primary),
        primary: true,
      },
    ];
  };
  const rowOf = (row: Schemas["LeaderboardRow"]) => (
    <LeaderboardRow
      key={row.solution_id}
      rank={row.rank}
      author={authors.row(row.author)}
      cells={cells(row)}
      me={row.is_me}
      duplicates={row.duplicates}
      duplicateOf={row.duplicate_of ? authors.of(row.duplicate_of.author) : null}
      href={solutionHref(row.solution_id)}
    />
  );
  const meShown = items.some((row) => row.is_me);
  return (
    <div className="flex flex-col">
      <div className="flex items-baseline justify-between gap-2 px-3.5 pt-3 pb-2">
        <h2 className="font-mono text-label text-mu uppercase">
          {t("title", { metric: primary === undefined ? "" : words.name(primary) })}
        </h2>
        <span className="text-caption text-mu">{t("entries", { count: entries })}</span>
      </div>
      <table aria-label={t("label")} className="w-full border-collapse text-[12.5px]">
        <tbody>
          {items.map(rowOf)}
          {me !== null && !meShown && (
            <>
              <LeaderboardGap columns={4} />
              {rowOf(me)}
            </>
          )}
        </tbody>
      </table>
      {me === null && (
        <p className="mx-3.5 mt-3 flex gap-2 rounded-md border border-bd bg-sf2 px-3 py-2.5 text-caption">
          <Info size={14} aria-hidden="true" className="mt-0.5 flex-none text-mu" />
          <span>
            {guest
              ? t.rich("guest", {
                  login: (chunks) => (
                    <Link href={loginHref(`/problems/${problem}`)} className="text-ac underline">
                      {chunks}
                    </Link>
                  ),
                })
              : t.rich("noPlace", { link })}
          </span>
        </p>
      )}
      <p className="flex justify-end px-3.5 py-3 text-caption">
        <Link href={full} className="inline-flex items-center gap-1 text-ac underline">
          {t("full")}
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </p>
    </div>
  );
}
