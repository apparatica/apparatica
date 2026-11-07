"use client";

// The block «Эталон» at the end of the statement on phones (FR-MOB-03, mock-up MobTask): the
// metrics of the best reference solution — public whatever the visibility of its code — and the
// code itself, the tab «Эталон» of a computer rendered by the server, under «Показать код
// эталона»; or why the code is closed. Phones have no «Сравнить с эталоном»: there is no editor
// there, and the diff needs a wide window.
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { getLeaderboardTop, leaderboardKeys } from "@/features/leaderboard/api";
import { useMetricWords } from "@/features/leaderboard/metrics";
import type { Schemas } from "@/lib/api/client";

import { type BenchReference, ReferenceTab } from "./reference-tab";

/** Metrics in the line of the block, as in the mock-up. */
const LINE_METRICS = 3;

function MetricsLine({ problem }: { problem: Pick<Schemas["ProblemDetail"], "slug"> }) {
  const t = useTranslations("reference.phone");
  const words = useMetricWords();
  const top = useQuery({
    queryKey: leaderboardKeys.top(problem.slug),
    queryFn: () => getLeaderboardTop(problem.slug),
  });
  if (top.isPending) return <Skeleton className="h-4 w-56" />;
  // Without the leaderboard the block still opens the code.
  if (top.isError) return null;
  const { reference, columns } = top.data;
  if (reference === null) return <p className="text-caption text-mu">{t("unmeasured")}</p>;
  const keys = [
    ...columns,
    ...Object.keys(reference.metrics)
      .sort()
      .filter((key) => !columns.includes(key)),
  ].filter((key) => reference.metrics[key] !== undefined);
  return (
    <p className="font-mono text-[13px]">
      {keys
        .slice(0, LINE_METRICS)
        .map((key) => words.inline(key, reference.metrics[key] as number))
        .join(" · ")}
    </p>
  );
}

export function PhoneReference({
  problem,
  reference,
}: {
  problem: Pick<Schemas["ProblemDetail"], "slug" | "leaderboard">;
  reference: BenchReference;
}) {
  const t = useTranslations("reference.phone");
  const [shown, show] = useState(false);
  const code = useId();
  const Chevron = shown ? ChevronDown : ChevronRight;
  return (
    <section aria-label={t("label")} className="flex flex-col gap-3 pb-4">
      <div className="mx-4 flex flex-col gap-1.5 rounded-md border border-bd bg-sf2 px-3.5 py-3">
        <h2 className="font-mono text-label text-mu uppercase">{t("label")}</h2>
        {problem.leaderboard !== null && <MetricsLine problem={problem} />}
        {reference.state === "locked" && <p className="text-caption text-mu">{t("locked")}</p>}
        {reference.state === "open" && (
          <button
            type="button"
            aria-expanded={shown}
            aria-controls={code}
            onClick={() => show(!shown)}
            className="-mx-1 inline-flex min-h-11 cursor-pointer items-center gap-1 self-start px-1 text-ac underline"
          >
            <Chevron size={14} aria-hidden="true" />
            {shown ? t("hide") : t("show")}
          </button>
        )}
      </div>
      {reference.state === "failed" && <ReferenceTab reference={reference} />}
      {reference.state === "open" && (
        <div id={code} hidden={!shown} className="border-y border-bd">
          {shown && reference.view}
        </div>
      )}
    </section>
  );
}
