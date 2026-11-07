"use client";

// The public solutions of a user (FR-USR-04), «Все N» of the profile: newest first, with the
// metrics and the place in the leaderboard of the problem pages show now, and pages.
import { ArrowLeft, FileX } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageState } from "@/components/domain/page-state";
import { Pagination } from "@/components/ui/pagination";

import { profileHref, userSolutionsHref } from "./href";
import type { UserSolutionsData } from "./load";
import { SolutionItem } from "./solution-item";

const number = (chunks: React.ReactNode) => <span className="text-tx">{chunks}</span>;

export function UserSolutionsPage({ nick, solutions }: UserSolutionsData) {
  const t = useTranslations("profile.solutionsPage");
  const { items, page, per_page: perPage, total } = solutions;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const from = (page - 1) * perPage + 1;
  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-title-1">{t("title", { nick })}</h1>
        <p className="text-mu">{t("subtitle", { count: total })}</p>
      </header>
      {total === 0 ? (
        <PageState
          icon={FileX}
          title={t("empty")}
          description={t("emptyText")}
          className="rounded-md border border-bd bg-sf"
        />
      ) : (
        <section
          aria-label={t("label", { nick })}
          className="rounded-md border border-bd bg-sf px-4 py-1"
        >
          <ul>
            {items.map((item) => (
              <SolutionItem key={item.id} item={item} />
            ))}
          </ul>
        </section>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 text-caption text-mu">
        <Link
          href={profileHref(nick)}
          className="inline-flex items-center gap-1 text-ac underline-offset-2 hover:underline"
        >
          <ArrowLeft size={12} aria-hidden="true" />
          {t("profile")}
        </Link>
        {items.length > 0 && (
          <span>{t.rich("shown", { from, to: from + items.length - 1, total, n: number })}</span>
        )}
        {pages > 1 && (
          <Pagination page={page} count={pages} href={(item) => userSolutionsHref(nick, item)} />
        )}
      </div>
    </div>
  );
}
