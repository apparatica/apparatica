// A public solution (FR-SOL-01/02, mock-up Solution): «Решение ‹ник›» with the problem, its
// level and the time of the Submit; the code read-only on the left — or a lock until the visitor's
// own accepted Submit of the problem; on the right the author, the verdict with the stages passed,
// «Совпадает с решением ‹ник›» of a duplicate, the place in the leaderboard and the metrics of the
// synthesis against the first place and the reference. Rendered by the server: the code is
// highlighted there. «Пожаловаться» comes with the complaints (phase 5).
import { ArrowRight, CircleCheck, Link2, Lock } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CodeViewer } from "@/components/domain/code-viewer";
import { type Difficulty, DifficultyBadge } from "@/components/domain/difficulty-badge";
import { PIPELINE_BLOCKS } from "@/components/domain/pipeline";
import { SvCode } from "@/components/domain/sv-code";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { solutionFile } from "@/features/editor/languages";
import { isMetricName, metricOf } from "@/features/leaderboard/metrics";
import { leaderboardHref } from "@/features/leaderboard/query";
import { SynthCards } from "@/features/leaderboard/synth-cards";
import { blockOf } from "@/features/problem/pipeline-view";
import { useAuthorNames } from "@/features/profile/author";
import { solutionCard } from "@/features/share/card";
import { ShareButton } from "@/features/share/share-dialog";
import type { Schemas } from "@/lib/api/client";
import { shortHref } from "@/lib/short-id";
import { cn } from "@/lib/utils";

import { solutionHref } from "./href";

type Solution = Schemas["Solution"];

export type SolutionProblem = Pick<
  Schemas["ProblemDetail"],
  "slug" | "title" | "version" | "top" | "language" | "reference" | "leaderboard"
>;

export interface SolutionPageProps {
  solution: Solution;
  /** The problem as it is now: the solution may be of an older version. */
  problem: SolutionProblem;
  level: { difficulty: Difficulty; rank: number } | null;
}

const problemHrefOf = (slug: string) => `/problems/${encodeURIComponent(slug)}`;

function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={cn("flex flex-col gap-1.5 rounded-md border border-bd bg-sf p-3.5", className)}
    >
      {children}
    </section>
  );
}

function LockedCode({ problemHref }: { problemHref: string }) {
  const t = useTranslations("solution.locked");
  return (
    <section className="flex flex-col items-center gap-2.5 rounded-md border border-bd bg-sf px-6 py-12 text-center">
      <div
        aria-hidden="true"
        className="mb-3 flex w-full max-w-[320px] flex-col gap-2 rounded-md border border-bd bg-ed p-4 blur-[1.5px]"
      >
        {[70, 92, 58, 84, 46, 76, 64].map((width, index) => (
          <span key={index} className="h-2 rounded-sm bg-sf2" style={{ width: `${width}%` }} />
        ))}
      </div>
      <Lock size={22} aria-hidden="true" className="text-mu" />
      <h2 className="text-[14px] font-medium">{t("title")}</h2>
      <p className="max-w-[420px] text-mu">{t("body")}</p>
      <p className="max-w-[420px] text-caption text-mu">{t("why")}</p>
      <Button variant="primary" asChild className="mt-1">
        <Link href={problemHref}>{t("solve")}</Link>
      </Button>
    </section>
  );
}

function AuthorCard({ author }: { author: Solution["author"] }) {
  const t = useTranslations("solution.author");
  const format = useFormatter();
  const authors = useAuthorNames();
  const profile = authors.href(author);
  const since = format.dateTime(new Date(author.created_at), {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return (
    <Card className="flex-row items-center gap-3">
      <Avatar name={authors.name(author)} size={40} className="rounded-sm" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">{authors.name(author)}</span>
        {profile !== null && (
          <span className="text-caption text-mu">
            {t("since", { date: since })} · {t("solved", { count: author.solved })}
          </span>
        )}
      </div>
      {profile !== null && (
        <Button asChild>
          <Link href={profile}>{t("profile")}</Link>
        </Button>
      )}
    </Card>
  );
}

/** «Линт, симуляция (32 из 32 тестов) и синтез пройдены. Замечаний линта нет.» */
function useVerdictText(stages: Solution["stages"]): string {
  const t = useTranslations("solution.verdict");
  const format = useFormatter();
  const blocks = PIPELINE_BLOCKS.filter((block) =>
    stages.some((stage) => blockOf(stage) === block),
  );
  const tests = stages
    .filter((stage) => blockOf(stage) === "sim" && stage.tests !== null)
    .reduce(
      (sum, stage) => ({
        passed: sum.passed + (stage.tests?.passed ?? 0),
        total: sum.total + (stage.tests?.total ?? 0),
      }),
      { passed: 0, total: 0 },
    );
  const names = blocks.map((block) =>
    block === "sim" && tests.total > 0 ? t("simTests", tests) : t(`blocks.${block}`),
  );
  const warned = PIPELINE_BLOCKS.filter((block) =>
    stages.some((stage) => blockOf(stage) === block && stage.status === "warning"),
  );
  const sentences: string[] = [];
  if (names.length > 0) {
    const passed = t("passed", { list: format.list(names), count: names.length });
    sentences.push(passed.charAt(0).toUpperCase() + passed.slice(1));
  }
  if (warned.length > 0) {
    sentences.push(t("warnings", { list: format.list(warned.map((block) => t(`of.${block}`))) }));
  } else if (blocks.includes("lint")) {
    sentences.push(t("noLint"));
  }
  return sentences.join(" ");
}

function VerdictCard({ solution }: { solution: Solution }) {
  const t = useTranslations("solution.verdict");
  const text = useVerdictText(solution.stages);
  return (
    <Card>
      <h2 className="flex items-center gap-2 font-medium text-ok">
        <CircleCheck size={16} aria-hidden="true" />
        {solution.status === "accepted" ? t("accepted") : t("acceptedWarnings")}
      </h2>
      {text !== "" && <p className="text-caption text-mu">{text}</p>}
    </Card>
  );
}

function DuplicateCard({ duplicate }: { duplicate: NonNullable<Solution["duplicate_of"]> }) {
  const t = useTranslations("solution.duplicate");
  const authors = useAuthorNames();
  return (
    <section className="flex gap-2.5 rounded-md border border-in bg-ins p-3.5">
      <Link2 size={16} aria-hidden="true" className="mt-0.5 flex-none text-in" />
      <div className="flex min-w-0 flex-col gap-1">
        <h2 className="font-medium">
          {t.rich("title", {
            link: (chunks) => (
              <Link href={solutionHref(duplicate.solution_id)} className="text-in underline">
                {chunks}
              </Link>
            ),
            nick: authors.of(duplicate.author),
          })}
        </h2>
        <p className="text-caption text-mu">{t("body")}</p>
      </div>
    </section>
  );
}

function PlaceCard({ solution, problem }: { solution: Solution; problem: SolutionProblem }) {
  const t = useTranslations("solution.place");
  const names = useTranslations("leaderboard");
  const main = solution.order[0] === undefined ? null : metricOf(solution.order[0].metric);
  const by = main !== null && isMetricName(main) ? names(`by.${main}`).toLowerCase() : null;
  const { placement } = solution;
  let body: ReactNode;
  if (placement !== null) {
    body = (
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-metric">{placement.rank}</span>
        <span className="text-caption text-mu">
          {[t("of", { total: placement.total }), by].filter((item) => item !== null).join(" · ")}
        </span>
      </p>
    );
  } else if (solution.version !== problem.version) {
    body = (
      <p className="text-caption text-mu">
        {t("oldVersion", { version: solution.version, current: problem.version })}
      </p>
    );
  } else {
    body = <p className="text-caption text-mu">{t("notEntry")}</p>;
  }
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-mono text-label text-mu uppercase">{t("title")}</h2>
        <Link
          href={leaderboardHref(problem.slug)}
          className="inline-flex items-center gap-1 text-caption text-ac underline"
        >
          {t("board")}
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
      </div>
      {body}
    </Card>
  );
}

function Metrics({ solution, problem }: { solution: Solution; problem: SolutionProblem }) {
  const t = useTranslations("solution");
  const synth = solution.stages.find((stage) => stage.type === "synth");
  if (synth === undefined || Object.keys(synth.metrics).length === 0) return null;
  return (
    <section aria-label={t("metrics")}>
      <SynthCards
        stage={synth.key}
        metrics={synth.metrics}
        reference={solution.reference ?? null}
        best={solution.best ?? null}
        order={solution.order}
        note={problem.reference === null ? t("note.noReference") : t("note.unmeasured")}
      />
    </section>
  );
}

export function SolutionPage({ solution, problem, level }: SolutionPageProps) {
  const t = useTranslations("solution");
  const problemWords = useTranslations("problem");
  const format = useFormatter();
  const authors = useAuthorNames();
  const problemHref = problemHrefOf(problem.slug);
  const submitted = format.dateTime(new Date(solution.submitted_at), {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  // A language without a title in the messages is shown by its key.
  const languageKey = `language.${solution.language}` as "language.systemverilog";
  const language = problemWords.has(languageKey) ? problemWords(languageKey) : solution.language;
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-title-1">{t("title", { nick: authors.of(solution.author) })}</h1>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-mu">
            <Link href={problemHref} className="hover:text-tx hover:underline">
              {problem.title}
            </Link>
            {level !== null && <DifficultyBadge difficulty={level.difficulty} rank={level.rank} />}
            {/* Phones put the time on a line of its own, without the dot. */}
            <span className="max-sm:basis-full">
              <span className="max-sm:hidden">· </span>
              {t("submitted", { date: submitted })}
            </span>
            {solution.version !== problem.version && (
              <span className="font-mono text-label" title={t("versionHint")}>
                · {t("version", { version: solution.version })}
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ShareButton
            card={solutionCard(solution, level, authors)}
            href={shortHref(solution.id)}
          />
          <Button variant="primary" asChild>
            <Link href={problemHref}>
              {t("openProblem")}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </header>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        {solution.code === null ? (
          <LockedCode problemHref={problemHref} />
        ) : (
          <CodeViewer
            fileName={solutionFile(problem.top, solution.language)}
            language={language}
            code={solution.code}
          >
            {solution.language === "systemverilog" ? <SvCode code={solution.code} /> : undefined}
          </CodeViewer>
        )}
        <aside aria-label={t("about")} className="flex flex-col gap-2.5">
          <AuthorCard author={solution.author} />
          <VerdictCard solution={solution} />
          {solution.duplicate_of !== null && <DuplicateCard duplicate={solution.duplicate_of} />}
          {solution.order.length > 0 && <PlaceCard solution={solution} problem={problem} />}
          <Metrics solution={solution} problem={problem} />
          {solution.code !== null && (
            <p className="flex gap-2 text-caption text-mu">
              <Lock size={14} aria-hidden="true" className="mt-0.5 flex-none" />
              {t("open")}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
