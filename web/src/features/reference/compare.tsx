"use client";

// «Сравнить с эталоном» (FR-REF-02; no mock-up, specs/08 §6): a wide dialog over the problem page
// with the own code and a reference solution side by side in Monaco's diff view, read-only, and a
// table of the metrics — the own, the reference's and the first place's. The own side is the
// accepted Submit on screen (its code and its synthesis), else the code of the editor, which has
// no metrics yet. The banner of an accepted Submit and the tab «Эталон» open it.
import { skipToken, useQuery } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { createContext, type ReactNode, useContext } from "react";

import { ComparisonText } from "@/components/domain/metric-card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { editorLanguage } from "@/features/editor/languages";
import { getLeaderboardTop, leaderboardKeys } from "@/features/leaderboard/api";
import {
  compareMetric,
  directionOf,
  METRIC_NAMES,
  metricOf,
  useMetricWords,
} from "@/features/leaderboard/metrics";
import { getSubmission, submissionKeys } from "@/features/submission/api";
import type { Stage } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

const DiffViewer = dynamic(() => import("@/features/editor/diff-viewer"), {
  ssr: false,
  loading: () => <DiffSkeleton />,
});

type Metrics = Record<string, number>;
type Reference = Schemas["ReferenceSolution"];

/** What the reference is compared with. */
export type Mine =
  /** An accepted Submit: its code is read from the API, its metrics from its synthesis. */
  | { kind: "submit"; id: string; synth: Stage | undefined }
  /** The code of the editor when the comparison opened. */
  | { kind: "draft"; code: string };

export interface CompareApi {
  /** Opens the comparison with a reference solution, by its index. */
  open: (reference: number) => void;
}

const CompareContext = createContext<CompareApi | null>(null);

/** The problem page gives it when the reference is open to the visitor. */
export const CompareProvider = CompareContext.Provider;

/** null where there is nothing to compare with. */
export const useCompare = (): CompareApi | null => useContext(CompareContext);

/** «Сравнить с эталоном»: nothing where the reference is closed. */
export function CompareButton({
  reference = 0,
  variant = "default",
  children,
}: {
  reference?: number;
  variant?: "default" | "primary";
  children?: ReactNode;
}) {
  const t = useTranslations("reference.compare");
  const compare = useCompare();
  if (compare === null) return null;
  return (
    <Button variant={variant} onClick={() => compare.open(reference)}>
      {variant === "default" && <GitCompareArrows aria-hidden="true" />}
      {children ?? t("open")}
    </Button>
  );
}

function DiffSkeleton() {
  return (
    <div aria-busy="true" className="flex h-full flex-col gap-2 p-3">
      {[64, 82, 40, 76, 58, 70].map((width, index) => (
        <Skeleton key={index} className="h-3" style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}

/** The metrics of a synthesis stage of a check, by `<stage key>.<metric>`. */
export function stageMetrics(stage: Stage | undefined): Metrics | null {
  if (stage === undefined) return null;
  const metrics: Metrics = {};
  for (const [metric, value] of Object.entries(stage.metrics)) {
    if (typeof value === "number") metrics[`${stage.key}.${metric}`] = value;
  }
  return Object.keys(metrics).length === 0 ? null : metrics;
}

/** The rows of the table: the metrics of the formula first, then the named ones in their order,
 * then any other. */
export function metricRows(
  order: readonly Schemas["LeaderboardKey"][] | undefined,
  ...sources: (Metrics | null)[]
): string[] {
  const keys = new Set(sources.flatMap((source) => Object.keys(source ?? {})));
  const formula = (order ?? []).map(({ metric }) => metric);
  const rank = (key: string) => {
    const inFormula = formula.indexOf(key);
    if (inFormula >= 0) return inFormula;
    const named = (METRIC_NAMES as readonly string[]).indexOf(metricOf(key));
    return named >= 0 ? formula.length + named : Number.MAX_SAFE_INTEGER;
  };
  return [...keys].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export interface CompareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  references: readonly Reference[];
  /** The reference solution shown; the others are a click away. */
  index: number;
  onIndex: (index: number) => void;
  mine: Mine;
  problem: Pick<Schemas["ProblemDetail"], "slug" | "language" | "leaderboard">;
}

function MetricTable({
  mine,
  reference,
  best,
  order,
}: {
  mine: Metrics | null;
  reference: Metrics | null;
  best: Metrics | null;
  order: readonly Schemas["LeaderboardKey"][] | undefined;
}) {
  const t = useTranslations("reference.compare.table");
  const words = useMetricWords();
  const rows = metricRows(order, mine, reference, best);
  if (rows.length === 0) return <p className="text-caption text-mu">{t("none")}</p>;
  const cell = (key: string, value: number | undefined) =>
    value === undefined ? "—" : words.value(key, value);
  return (
    <table aria-label={t("label")} className="w-full border-collapse text-[12.5px]">
      <thead>
        <tr className="border-b border-bd text-left font-mono text-label text-mu uppercase">
          <th scope="col" className="py-1.5 pr-3 font-normal">
            {t("metric")}
          </th>
          <th scope="col" className="px-3 py-1.5 text-right font-normal">
            {t("mine")}
          </th>
          <th scope="col" className="px-3 py-1.5 text-right font-normal">
            {t("reference")}
          </th>
          <th scope="col" className="py-1.5 pl-3 text-right font-normal">
            {t("best")}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((key) => {
          const own = mine?.[key];
          const theirs = reference?.[key];
          const unit = words.unit(key);
          return (
            <tr key={key} className="border-b border-bd last:border-b-0">
              <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                {words.name(key)}
                {unit !== null && <span className="text-mu">, {unit}</span>}
              </th>
              <td className="px-3 py-1.5 text-right">
                <span className="font-mono tabular-nums">{cell(key, own)}</span>
                {own !== undefined && theirs !== undefined && (
                  <span className="ml-2 inline-block">
                    <ComparisonText
                      comparison={compareMetric(own, theirs, directionOf(key, order))}
                    />
                  </span>
                )}
              </td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums">{cell(key, theirs)}</td>
              <td className="py-1.5 pl-3 text-right font-mono tabular-nums">
                {cell(key, best?.[key])}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function CompareDialog({
  open,
  onOpenChange,
  references,
  index,
  onIndex,
  mine,
  problem,
}: CompareDialogProps) {
  const t = useTranslations("reference.compare");
  const reference = references[index] ?? references[0];
  const submit = useQuery({
    queryKey: mine.kind === "submit" ? submissionKeys.detail(mine.id) : ["compare", "draft"],
    queryFn: open && mine.kind === "submit" ? () => getSubmission(mine.id) : skipToken,
    staleTime: Infinity,
  });
  const ranked = problem.leaderboard !== null;
  const top = useQuery({
    queryKey: leaderboardKeys.top(problem.slug),
    queryFn: open && ranked ? () => getLeaderboardTop(problem.slug) : skipToken,
  });
  if (reference === undefined) return null;

  const code = mine.kind === "draft" ? mine.code : (submit.data?.code ?? null);
  const metrics = mine.kind === "submit" ? stageMetrics(mine.synth) : null;
  const mineLabel = mine.kind === "submit" ? t("mineSubmit") : t("mineDraft");
  let diff: ReactNode;
  if (code !== null) {
    diff = (
      <DiffViewer
        original={code}
        modified={reference.code}
        language={editorLanguage(problem.language).monaco}
        label={t("diffLabel", { mine: mineLabel, reference: reference.title })}
        loading={<DiffSkeleton />}
      />
    );
  } else if (submit.isError) {
    diff = (
      <div className="flex h-full flex-col items-center justify-center gap-2.5 p-6 text-center">
        <p className="text-mu">{t("failed")}</p>
        <Button onClick={() => void submit.refetch()}>{t("retry")}</Button>
      </div>
    );
  } else {
    diff = <DiffSkeleton />;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[calc(100dvh-32px)] max-h-[880px] max-w-[1180px]">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {mine.kind === "submit"
              ? t("describeSubmit", { reference: reference.title })
              : t("describeDraft", { reference: reference.title })}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 px-5 py-4">
          {references.length > 1 && (
            <div role="group" aria-label={t("choose")} className="flex flex-wrap gap-1.5">
              {references.map((item, at) => (
                <Button
                  key={at}
                  variant={at === index ? "outline" : "default"}
                  aria-pressed={at === index}
                  onClick={() => onIndex(at)}
                >
                  {item.title}
                </Button>
              ))}
            </div>
          )}
          <div className="flex flex-none items-center font-mono text-label text-mu uppercase">
            <span className="flex-1">{mineLabel}</span>
            <span className="flex-1 pl-4">{t("referenceSide", { title: reference.title })}</span>
          </div>
          <div className="min-h-[200px] flex-1 overflow-hidden rounded-md border border-bd bg-ed">
            {diff}
          </div>
          <div className={cn("flex-none overflow-x-auto", "max-h-[40%]")}>
            <MetricTable
              mine={metrics}
              reference={reference.metrics ?? null}
              best={top.data?.best?.metrics ?? null}
              order={problem.leaderboard?.order}
            />
            {mine.kind === "draft" && (
              <p className="mt-2 text-caption text-mu">{t("draftMetrics")}</p>
            )}
            {reference.metrics === null && (
              <p className="mt-2 text-caption text-mu">{t("unmeasured")}</p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
