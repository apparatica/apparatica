"use client";

// The catalogue on phones (FR-MOB-01, mock-up MobCatalog): a card per problem instead of the table —
// the number, the title, the level, the acceptance rate and the tags; the status on the right. The
// whole card opens the problem.
import Link from "next/link";
import { useTranslations } from "next-intl";

import { DifficultyBadge, findDifficulty } from "@/components/domain/difficulty-badge";
import { TagChip } from "@/components/domain/tag-chip";
import { Skeleton } from "@/components/ui/skeleton";
import type { History } from "@/features/guest/history";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { ProblemStatus } from "./problem-table";
import { statusOf } from "./view";

export function ProblemList({
  problems,
  levels,
  tags,
  history,
  rows,
  busy,
}: {
  /** Null while unknown: placeholder cards. */
  problems: Schemas["ProblemListItem"][] | null;
  levels: Schemas["Difficulty"][];
  tags: Schemas["Tag"][];
  history: History | null;
  /** How many placeholder cards. */
  rows: number;
  /** A new query is loading: the cards are those of the previous one. */
  busy: boolean;
}) {
  const t = useTranslations("problems.list");
  const titleOf = (slug: string) => tags.find((tag) => tag.slug === slug)?.title ?? slug;
  return (
    <ul
      aria-label={t("label")}
      aria-busy={busy || problems === null || undefined}
      className={cn("-mx-4 border-y border-bd transition-opacity", busy && "opacity-60")}
    >
      {problems === null
        ? Array.from({ length: rows }, (_, index) => (
            <li key={index} className="flex gap-3 border-t border-bd px-4 py-3.5 first:border-t-0">
              <Skeleton className="h-3.5 w-5" />
              <span className="flex flex-1 flex-col gap-2">
                <Skeleton className="h-3.5 w-48" />
                <Skeleton className="h-3 w-36" />
              </span>
            </li>
          ))
        : problems.map((problem) => {
            const level = findDifficulty(levels, problem.difficulty);
            return (
              <li
                key={problem.slug}
                className="relative flex items-center gap-3 border-t border-bd px-4 py-3.5 first:border-t-0 focus-within:bg-sf2 active:bg-sf2"
              >
                <span className="w-6 flex-none self-start font-mono text-mu">{problem.number}</span>
                <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <Link
                    href={`/problems/${problem.slug}`}
                    className="font-medium after:absolute after:inset-0 after:content-['']"
                  >
                    {problem.title}
                  </Link>
                  <span className="flex min-w-0 items-center gap-2 overflow-hidden">
                    {level ? (
                      <DifficultyBadge difficulty={level.difficulty} rank={level.rank} />
                    ) : (
                      <span className="font-mono text-mu">{problem.difficulty}</span>
                    )}
                    {problem.acceptance !== null && (
                      <span className="flex-none font-mono text-caption whitespace-nowrap text-mu">
                        {t("acceptance", { value: Math.round(problem.acceptance * 100) })}
                      </span>
                    )}
                    {problem.tags.map((tag) => (
                      <TagChip key={tag} className="min-w-0">
                        <span className="truncate">{titleOf(tag)}</span>
                      </TagChip>
                    ))}
                  </span>
                </span>
                <span className="w-[76px] flex-none">
                  {history === null ? (
                    <Skeleton className="ml-auto h-3.5 w-14" />
                  ) : (
                    <ProblemStatus status={statusOf(history, problem.slug)} stacked />
                  )}
                </span>
              </li>
            );
          })}
    </ul>
  );
}
