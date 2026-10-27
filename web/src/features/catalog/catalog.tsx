"use client";

// The catalogue page (specs/08 §1, mock-up Catalog): progress summary, controls, table, pages.
// The server renders the query of the address; a change of the controls replaces the address in
// a transition, so the controls show the new query at once and the rows wait for the server.
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useOptimistic, useTransition } from "react";

import { Pagination } from "@/components/ui/pagination";
import { useHistory } from "@/features/guest/history";

import { CatalogFilters } from "./filters";
import type { CatalogData } from "./load";
import { EmptyCatalog, ProblemTable } from "./problem-table";
import { ProgressSummary } from "./progress";
import { type CatalogQuery, catalogHref, hasFilters, withoutFilters } from "./query";
import { catalogView } from "./view";

export function Catalog({ query, data }: { query: CatalogQuery; data: CatalogData }) {
  const t = useTranslations("problems");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [shown, show] = useOptimistic(query);
  const history = useHistory();
  const view = catalogView(data, query, history);

  const navigate = (next: CatalogQuery) =>
    startTransition(() => {
      show(next);
      router.replace(catalogHref(next), { scroll: false });
    });

  const from = (query.page - 1) * data.perPage;
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-6 pb-4 sm:px-8">
      <div className="flex flex-col gap-0.5">
        <h1 className="text-title-1">{t("title")}</h1>
        <p className="text-mu">{t("subtitle")}</p>
      </div>
      <ProgressSummary levels={data.levels} progress={data.progress} history={history} />
      <CatalogFilters
        query={shown}
        levels={data.levels}
        tags={data.tags}
        total={view?.total ?? null}
        onChange={navigate}
      />
      {view !== null && view.total === 0 ? (
        <EmptyCatalog
          q={query.q}
          filtered={hasFilters(query)}
          resetHref={catalogHref(withoutFilters(query))}
        />
      ) : (
        <ProblemTable
          problems={view?.problems ?? null}
          levels={data.levels}
          tags={data.tags}
          history={history}
          rows={data.perPage}
          busy={busy}
        />
      )}
      {view !== null && view.total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-mu">
          <span>
            {t.rich("shown", {
              from: Math.min(from + 1, view.total),
              to: Math.min(from + view.problems.length, view.total),
              total: view.total,
              n: (chunks) => <span className="font-mono text-tx">{chunks}</span>,
            })}
          </span>
          <Pagination
            page={query.page}
            count={view.pages}
            href={(page) => catalogHref({ ...query, page })}
          />
        </div>
      )}
    </div>
  );
}
