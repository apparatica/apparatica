// The statement panel of a problem page (FR-PRB-02/03, mock-up Bench): the header with the title,
// level, tags and acceptance rate, then the statement and the ports of the interface. Rendered by
// the server, so the statement is in the HTML without JavaScript (FR-PRB-04). Phones (mock-up
// MobTask) have the title in the header.
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { DifficultyBadge, findDifficulty } from "@/components/domain/difficulty-badge";
import { PortTable } from "@/components/domain/port-table";
import { TagChip } from "@/components/domain/tag-chip";
import { Statement } from "@/lib/statement/statement";

import type { ProblemData } from "./load";

/** Pictures of the statement, `assets/…`, from the API by version: they never change. */
function assetUrl(slug: string, version: number): (path: string) => string {
  const base = `/api/v1/problems/${encodeURIComponent(slug)}/versions/${version}`;
  return (path) => `${base}/${path.split("/").map(encodeURIComponent).join("/")}`;
}

export function ProblemStatement({ problem, levels, tags }: ProblemData) {
  const t = useTranslations("problem");
  const level = findDifficulty(levels, problem.difficulty);
  const titleOf = (slug: string) => tags.find((tag) => tag.slug === slug)?.title ?? slug;
  const value = (chunks: ReactNode) => <span className="font-mono text-tx">{chunks}</span>;
  return (
    <article>
      <header className="flex flex-col gap-2.5 border-b border-bd px-4 pt-3.5 pb-3.5 sm:px-[22px] sm:pt-[18px]">
        <h1 className="text-[22px] leading-[30px] font-semibold tracking-[-0.01em] max-sm:sr-only">
          {problem.title}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5 pointer-coarse:gap-y-6">
          {level && <DifficultyBadge difficulty={level.difficulty} rank={level.rank} />}
          {problem.tags.map((tag) => (
            <TagChip key={tag} asChild className="touch-target">
              <Link href={{ pathname: "/problems", query: { tag } }}>{titleOf(tag)}</Link>
            </TagChip>
          ))}
          <span className="ml-1.5 text-caption text-mu" title={t("acceptanceHint")}>
            {problem.acceptance === null
              ? t.rich("acceptanceUnknown", { value })
              : t.rich("acceptance", { value, percent: Math.round(problem.acceptance * 100) })}
          </span>
        </div>
      </header>
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-[22px]">
        <Statement
          markdown={problem.statement_md}
          assetUrl={assetUrl(problem.slug, problem.version)}
        />
        <PortTable ports={problem.interface.ports} />
      </div>
    </article>
  );
}
