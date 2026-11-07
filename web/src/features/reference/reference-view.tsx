// The open tab «Эталон» (FR-REF-01): every reference solution of the author with its title, the
// metrics on the default profile, the explanation of the microarchitecture and the code, and
// «Сравнить с эталоном». Rendered by the server like the statement: the page sends the HTML of
// the explanation and of the highlighted code, not the renderers.
import { useTranslations } from "next-intl";

import { CodeViewer } from "@/components/domain/code-viewer";
import { SvCode } from "@/components/domain/sv-code";
import { solutionFile } from "@/features/editor/languages";
import { METRIC_NAMES, metricOf, useMetricWords } from "@/features/leaderboard/metrics";
import { assetUrl } from "@/features/problem/problem-statement";
import type { Schemas } from "@/lib/api/client";
import { Statement } from "@/lib/statement/statement";

import { CompareButton } from "./compare";

export interface ReferenceViewProps {
  page: Schemas["ReferencePage"];
  problem: Pick<Schemas["ProblemDetail"], "slug" | "top" | "language">;
}

/** The named metrics in their order, then the others. */
const metricKeys = (metrics: Record<string, number>) =>
  Object.keys(metrics).sort((a, b) => {
    const rank = (key: string) => {
      const named = (METRIC_NAMES as readonly string[]).indexOf(metricOf(key));
      return named < 0 ? METRIC_NAMES.length : named;
    };
    return rank(a) - rank(b) || a.localeCompare(b);
  });

function ReferenceMetrics({ metrics }: { metrics: Record<string, number> | null }) {
  const t = useTranslations("reference");
  const words = useMetricWords();
  if (metrics === null) return <p className="text-caption text-mu">{t("unmeasured")}</p>;
  return (
    <dl aria-label={t("metrics")} className="flex flex-wrap gap-x-5 gap-y-1.5">
      {metricKeys(metrics).map((key) => (
        <div key={key} className="flex flex-col">
          <dt className="text-caption text-mu">{words.name(key)}</dt>
          <dd className="font-mono">
            {words.value(key, metrics[key] as number)}
            {words.unit(key) !== null && (
              <span className="ml-1 text-[11px] text-mu">{words.unit(key)}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ReferenceView({ page, problem }: ReferenceViewProps) {
  const t = useTranslations("reference");
  const languages = useTranslations("problem");
  const languageKey = `language.${problem.language}` as "language.systemverilog";
  const language = languages.has(languageKey) ? languages(languageKey) : problem.language;
  const file = solutionFile(problem.top, problem.language);
  return (
    <div className="flex flex-col">
      {page.solutions.map((solution, index) => (
        <article
          key={index}
          className="flex flex-col gap-3 border-b border-bd px-4 py-4 last:border-b-0 sm:px-[22px]"
        >
          <header className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="font-mono text-label text-mu uppercase">
                {page.solutions.length > 1
                  ? t("numbered", { number: index + 1, total: page.solutions.length })
                  : t("label")}
              </span>
              <h2 className="text-[15px] font-semibold">{solution.title}</h2>
            </div>
            <CompareButton reference={index} />
          </header>
          <ReferenceMetrics metrics={solution.metrics ?? null} />
          {solution.explanation_md !== null && (
            <Statement
              markdown={solution.explanation_md}
              assetUrl={assetUrl(problem.slug, page.version)}
            />
          )}
          <CodeViewer fileName={file} language={language} code={solution.code}>
            {problem.language === "systemverilog" ? <SvCode code={solution.code} /> : undefined}
          </CodeViewer>
        </article>
      ))}
      {page.visibility === "public" && (
        <p className="px-4 pb-4 text-caption text-mu sm:px-[22px]">{t("public")}</p>
      )}
    </div>
  );
}
