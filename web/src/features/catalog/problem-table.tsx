"use client";

// The table of the catalogue (FR-CAT-01): status, number and title, level, tags, acceptance rate;
// the whole row opens the problem. And the empty state of a query without problems (PageErrors).
import { Circle, CircleCheck, Contrast, SearchX } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { DifficultyBadge, findDifficulty } from "@/components/domain/difficulty-badge";
import { TagChip } from "@/components/domain/tag-chip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { History } from "@/features/guest/history";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { StatusFilter } from "./query";
import { statusOf } from "./view";

const STATUS_LOOK = {
  solved: { Icon: CircleCheck, className: "text-ok", iconClassName: "" },
  attempted: { Icon: Contrast, className: "text-tx", iconClassName: "text-mu" },
  not_started: { Icon: Circle, className: "text-mu", iconClassName: "" },
} as const;

export function ProblemStatus({ status }: { status: StatusFilter }) {
  const t = useTranslations("problems.status");
  const { Icon, className, iconClassName } = STATUS_LOOK[status];
  return (
    <span data-status={status} className={cn("flex items-center gap-2", className)}>
      <Icon size={15} aria-hidden="true" className={cn("flex-none", iconClassName)} />
      {t(status)}
    </span>
  );
}

const cell = "px-1.5 first:pl-4 last:pr-4";

function Header() {
  const t = useTranslations("problems.table");
  return (
    <thead>
      <tr className="h-[34px] bg-sf2 text-left font-mono text-label text-mu uppercase">
        <th scope="col" className={cn(cell, "font-normal")}>
          {t("status")}
        </th>
        <th scope="col" className={cn(cell, "font-normal")}>
          {t("title")}
        </th>
        <th scope="col" className={cn(cell, "font-normal")}>
          {t("difficulty")}
        </th>
        <th scope="col" className={cn(cell, "font-normal")}>
          {t("tags")}
        </th>
        <th scope="col" className={cn(cell, "text-right font-normal")}>
          {t("acceptance")}
        </th>
      </tr>
    </thead>
  );
}

function Acceptance({ value }: { value: number | null }) {
  const t = useTranslations("problems.table");
  if (value === null) {
    return (
      <>
        <span aria-hidden="true" className="text-mu">
          —
        </span>
        <span className="sr-only">{t("noAcceptance")}</span>
      </>
    );
  }
  return <>{t("percent", { value: Math.round(value * 100) })}</>;
}

export function ProblemTable({
  problems,
  levels,
  tags,
  history,
  rows,
  busy,
}: {
  /** Null while unknown: placeholder rows. */
  problems: Schemas["ProblemListItem"][] | null;
  levels: Schemas["Difficulty"][];
  tags: Schemas["Tag"][];
  history: History | null;
  /** How many placeholder rows. */
  rows: number;
  /** A new query is loading: the rows are those of the previous one. */
  busy: boolean;
}) {
  const t = useTranslations("problems.table");
  const titleOf = (slug: string) => tags.find((tag) => tag.slug === slug)?.title ?? slug;
  return (
    <div className="overflow-x-auto rounded-md border border-bd">
      <table
        aria-label={t("label")}
        aria-busy={busy || problems === null || undefined}
        className={cn(
          "w-full min-w-[760px] table-fixed border-collapse text-[12.5px] transition-opacity",
          busy && "opacity-60",
        )}
      >
        <colgroup>
          <col className="w-32" />
          <col />
          <col className="w-[120px]" />
          <col className="w-[290px]" />
          <col className="w-[96px]" />
        </colgroup>
        <Header />
        <tbody>
          {problems === null
            ? Array.from({ length: rows }, (_, index) => (
                <tr key={index} className="h-10 border-t border-bd">
                  {[20, 48, 16, 28, 8].map((width, column) => (
                    <td key={column} className={cell}>
                      <Skeleton
                        className={cn("h-3.5", column === 4 && "ml-auto")}
                        style={{ width: `${width * 4}px`, maxWidth: "100%" }}
                      />
                    </td>
                  ))}
                </tr>
              ))
            : problems.map((problem) => {
                const level = findDifficulty(levels, problem.difficulty);
                return (
                  <tr
                    key={problem.slug}
                    className="relative h-10 border-t border-bd focus-within:bg-sf2 hover:bg-sf2"
                  >
                    <td className={cell}>
                      {history === null ? (
                        <Skeleton className="h-3.5 w-20" />
                      ) : (
                        <ProblemStatus status={statusOf(history, problem.slug)} />
                      )}
                    </td>
                    <td className={cn(cell, "truncate")}>
                      <span className="mr-2 font-mono text-mu">{problem.number}</span>
                      <Link
                        href={`/problems/${problem.slug}`}
                        className="font-medium after:absolute after:inset-0 after:content-['']"
                      >
                        {problem.title}
                      </Link>
                    </td>
                    <td className={cell}>
                      {level ? (
                        <DifficultyBadge difficulty={level.difficulty} rank={level.rank} />
                      ) : (
                        <span className="font-mono text-mu">{problem.difficulty}</span>
                      )}
                    </td>
                    <td className={cell}>
                      <span className="flex gap-1 overflow-hidden">
                        {problem.tags.map((tag) => (
                          <TagChip key={tag}>{titleOf(tag)}</TagChip>
                        ))}
                      </span>
                    </td>
                    <td className={cn(cell, "text-right font-mono")}>
                      <Acceptance value={problem.acceptance} />
                    </td>
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}

/** No problem matches the query; or the catalogue has none. */
export function EmptyCatalog({
  q,
  filtered,
  resetHref,
}: {
  q: string;
  /** The search or a filter is on. */
  filtered: boolean;
  resetHref: string;
}) {
  const t = useTranslations("problems");
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-bd px-6 py-14 text-center">
      <SearchX size={22} aria-hidden="true" className="mb-2 text-mu" />
      <h2 className="text-title-2">{filtered ? t("empty.title") : t("empty.catalog")}</h2>
      <p className="max-w-[420px] text-mu">
        {!filtered
          ? t("empty.catalogHint")
          : q.trim() !== ""
            ? t("empty.query", { q: q.trim() })
            : t("empty.filters")}
      </p>
      {filtered && (
        <Button variant="primary" asChild className="mt-3">
          <Link href={resetHref}>{t("filters.reset")}</Link>
        </Button>
      )}
    </div>
  );
}
