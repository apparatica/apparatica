"use client";

// The leaderboard of a problem (FR-LB-01/03/04, mock-up SolutionLB): cards of the first place,
// the reference and the own entry; what the main metric means and how places are ordered; the
// table with a place, author, the metrics of `columns` and the date per row, sorted by a column
// without changing the places, with duplicates folded under the earliest solution; pages. The
// server renders the query of the address; the controls change it. Phones (FR-MOB-03, without a
// mock-up) keep the place, the author and one metric — of the sort, else the main one — and sort
// with a menu instead of the headers.
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  Info,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Fragment, type ReactNode, useOptimistic, useState, useTransition } from "react";

import { DifficultyBadge } from "@/components/domain/difficulty-badge";
import {
  type LeaderboardCell,
  LeaderboardGap,
  LeaderboardMember,
  LeaderboardRow,
  WIDE,
} from "@/components/domain/leaderboard-row";
import { PageState } from "@/components/domain/page-state";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Pagination } from "@/components/ui/pagination";
import { useGuest } from "@/features/account/session";
import { useAuthorNames } from "@/features/profile/author";
import { solutionHref } from "@/features/solution/href";
import { problemHref as problemHrefOf } from "@/features/problem/href";
import type { ProblemCard } from "@/features/share/card";
import { ShareButton } from "@/features/share/share-dialog";
import type { Schemas } from "@/lib/api/client";
import { loginHref } from "@/lib/session";
import { cn } from "@/lib/utils";

import { useShortDate } from "./date";
import { directionOf, isMetricName, metricOf, useMetricWords, useOrderWords } from "./metrics";
import { type BoardQuery, columnSort, leaderboardHref, phoneColumn, phoneSorts } from "./query";

export type BoardProblem = Pick<Schemas["ProblemDetail"], "slug" | "title" | "reference">;

export interface LeaderboardPageProps {
  problem: BoardProblem;
  /** The level of the problem; null for an unknown one. */
  level: { difficulty: Schemas["Difficulty"]; rank: number } | null;
  board: Schemas["ProblemLeaderboard"];
  query: BoardQuery;
  /** «Поделиться» shares the problem (FR-SHR-01). */
  card: ProblemCard;
}

/** Metrics of a summary card: the first columns, as in the mock-up. */
const CARD_METRICS = 4;
type Row = Schemas["LeaderboardRow"];

/** The cells of a row: the metrics of the columns, the first of the order being the main one;
 * phones show only the column `phone`. */
export function useCells(
  columns: readonly string[],
  primary: string | undefined,
  phone: string | undefined = undefined,
) {
  const words = useMetricWords();
  return (metrics: Row["metrics"], units = false): LeaderboardCell[] =>
    columns.map((key) => {
      const value = metrics[key];
      return {
        key,
        text: value === undefined ? "—" : words.value(key, value),
        unit: units ? words.unit(key) : null,
        primary: key === primary,
        wide: phone !== undefined && key !== phone,
      };
    });
}

function SummaryCard({
  title,
  aside,
  own = false,
  children,
}: {
  title: string;
  aside?: ReactNode;
  own?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className={cn(
        "flex min-w-0 flex-col gap-2.5 rounded-md border px-3.5 py-3",
        own ? "border-ac bg-acs" : "border-bd bg-sf",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2 className={cn("font-mono text-label uppercase", own ? "text-ac" : "text-mu")}>
          {title}
        </h2>
        {aside != null && <span className="truncate text-caption text-mu">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

function CardMetrics({
  columns,
  metrics,
}: {
  columns: readonly string[];
  metrics: Row["metrics"];
}) {
  const words = useMetricWords();
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2">
      {columns.slice(0, CARD_METRICS).map((key) => {
        const value = metrics[key];
        const unit = words.unit(key);
        return (
          <div key={key} className="flex flex-col">
            <dt className="truncate text-caption text-mu">{words.name(key)}</dt>
            <dd className="font-mono text-[17px] leading-6 font-medium whitespace-nowrap tabular-nums">
              {value === undefined ? "—" : words.value(key, value)}
              {unit !== null && value !== undefined && (
                <span className="ml-1 text-[11px] font-normal text-mu">{unit}</span>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function CardNote({ children }: { children: ReactNode }) {
  return <p className="text-caption text-mu">{children}</p>;
}

function Cards({ problem, board }: Pick<LeaderboardPageProps, "problem" | "board">) {
  const t = useTranslations("leaderboard.page.cards");
  const date = useShortDate();
  const guest = useGuest();
  const authors = useAuthorNames();
  const { best, reference, me, columns } = board;
  const problemHref = problemHrefOf(problem.slug);
  return (
    <div className="grid gap-2 lg:grid-cols-3">
      <SummaryCard
        title={t("best")}
        aside={best === null ? null : `${authors.name(best.author)} · ${date(best.submitted_at)}`}
      >
        {best === null ? (
          <CardNote>{t("noBest")}</CardNote>
        ) : (
          <CardMetrics columns={columns} metrics={best.metrics} />
        )}
      </SummaryCard>
      <SummaryCard
        title={t("reference")}
        aside={reference === null ? null : reference.title || t("referenceAside")}
      >
        {reference === null ? (
          <CardNote>{problem.reference === null ? t("noReference") : t("unmeasured")}</CardNote>
        ) : (
          <CardMetrics columns={columns} metrics={reference.metrics} />
        )}
      </SummaryCard>
      {me === null ? (
        <SummaryCard title={t("mine")}>
          <CardNote>
            {guest
              ? t.rich("guest", {
                  link: (chunks) => (
                    <Link href={loginHref(problemHref)} className="text-ac underline">
                      {chunks}
                    </Link>
                  ),
                })
              : t("noPlace")}
          </CardNote>
        </SummaryCard>
      ) : (
        <SummaryCard own title={t("minePlace", { rank: me.rank })} aside={date(me.submitted_at)}>
          <CardMetrics columns={columns} metrics={me.metrics} />
        </SummaryCard>
      )}
    </div>
  );
}

function SortHeader({
  label,
  unit,
  sort,
  href,
  primary,
  wide = false,
}: {
  label: string;
  unit: string | null;
  sort: ReturnType<typeof columnSort>;
  href: string;
  primary: boolean;
  /** Phones hide the column. */
  wide?: boolean;
}) {
  const t = useTranslations("leaderboard.page.table");
  const Icon = !sort.active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={sort.active ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
      className={cn("px-2 text-right font-normal last:pr-3.5", wide && WIDE)}
    >
      {/* The name starts with the visible text (WCAG 2.5.3); the accent of the active column is
          its arrow: accent text on the header falls short of 4.5:1. */}
      <Link
        href={href}
        scroll={false}
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap hover:text-tx",
          sort.active && "text-tx",
          primary && "font-medium",
        )}
      >
        <span>
          {label}
          {unit !== null && <span className="normal-case">, {unit}</span>}{" "}
          <span className="sr-only">{t("sortBy")}</span>
        </span>
        <Icon size={12} aria-hidden="true" className={cn(sort.active ? "text-ac" : "opacity-60")} />
      </Link>
    </th>
  );
}

function BoardTable({
  problem,
  board,
  query,
  busy,
}: Pick<LeaderboardPageProps, "problem" | "board" | "query"> & { busy: boolean }) {
  const t = useTranslations("leaderboard.page.table");
  const names = useTranslations("leaderboard");
  const words = useMetricWords();
  const date = useShortDate();
  const primary = board.order[0]?.metric;
  const phone = phoneColumn(query.sort, board.columns, board.order);
  const cells = useCells(board.columns, primary, phone);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const sortHref = (sort: string) =>
    leaderboardHref(problem.slug, { ...query, sort, page: 1, around: false });
  // The place, the author, the metrics, the date and the chevron to the solution.
  const columns = board.columns.length + 4;
  const authors = useAuthorNames();
  const meShown = board.items.some((row) => row.is_me);

  const rowOf = (row: Row) => (
    <LeaderboardRow
      rank={row.rank}
      author={authors.row(row.author)}
      cells={cells(row.metrics)}
      date={date(row.submitted_at)}
      me={row.is_me}
      id={row.is_me ? "me" : undefined}
      duplicates={row.duplicates}
      expanded={expanded.has(row.solution_id)}
      onToggle={() => toggle(row.solution_id)}
      duplicateOf={row.duplicate_of ? authors.of(row.duplicate_of.author) : null}
      href={solutionHref(row.solution_id)}
    />
  );

  return (
    <div className="overflow-x-auto rounded-md border border-bd">
      <table
        aria-label={t("label")}
        aria-busy={busy || undefined}
        className={cn(
          "w-full border-collapse text-[12.5px] transition-opacity sm:min-w-[720px]",
          busy && "opacity-60",
        )}
      >
        <thead>
          <tr className="h-[34px] border-b border-bd bg-sf2 text-left font-mono text-label text-mu uppercase">
            <th scope="col" className="w-12 px-2 pl-3.5 font-normal">
              {t("rank")}
            </th>
            <th scope="col" className="px-2 font-normal">
              {t("author")}
            </th>
            {board.columns.map((key) => {
              const sort = columnSort(key, query.sort, board.order);
              return (
                <SortHeader
                  key={key}
                  label={words.name(key)}
                  unit={words.unit(key)}
                  sort={sort}
                  href={sortHref(sort.next)}
                  primary={key === primary}
                  wide={key !== phone}
                />
              );
            })}
            <SortHeader
              label={t("date")}
              unit={null}
              sort={columnSort("submitted_at", query.sort, board.order)}
              href={sortHref(columnSort("submitted_at", query.sort, board.order).next)}
              primary={false}
              wide
            />
            <th scope="col" className="w-8">
              <span className="sr-only">{t("solution")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {board.items.map((row) => (
            <Fragment key={row.solution_id}>
              {rowOf(row)}
              {expanded.has(row.solution_id) &&
                row.group.map((member) => (
                  <LeaderboardMember
                    key={member.solution_id}
                    author={authors.row(member.author)}
                    leader={authors.of(row.author)}
                    cells={cells(row.metrics)}
                    date={date(member.submitted_at)}
                    href={solutionHref(member.solution_id)}
                  />
                ))}
              {expanded.has(row.solution_id) && row.duplicates > row.group.length && (
                <tr className="h-7 border-t border-bd bg-sf2 text-caption text-mu">
                  <td />
                  <td colSpan={columns - 1} className="px-2">
                    {names("moreDuplicates", { count: row.duplicates - row.group.length })}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {board.me !== null && !meShown && (
            <>
              <LeaderboardGap columns={columns} />
              {rowOf(board.me)}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Phones: the sort of the table as a menu; the headers of the hidden columns cannot sort. */
function SortMenu({
  board,
  sort,
  onSort,
}: {
  board: LeaderboardPageProps["board"];
  sort: string;
  onSort: (sort: string) => void;
}) {
  const t = useTranslations("leaderboard.page.sort");
  const names = useTranslations("leaderboard");
  const words = useMetricWords();
  const sorts = phoneSorts(board.columns, board.order);
  const labelOf = (value: string) => {
    if (value === "rank") return t("rank");
    if (value === "-submitted_at") return t("newest");
    if (value === "submitted_at") return t("oldest");
    const key = value.replace(/^-/, "");
    const metric = metricOf(key);
    const by = isMetricName(metric) ? names(`by.${metric}`) : words.name(key);
    const dir = value.startsWith("-") ? "desc" : "asc";
    return dir === directionOf(key, board.order) ? by : t("reversed", { by });
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label={t("label", { sort: labelOf(sort) })} className="sm:hidden">
          {labelOf(sort)}
          <ChevronDown className="size-3.5!" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("title")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={sort} onValueChange={onSort}>
          {sorts.map((value) => (
            <DropdownMenuRadioItem key={value} value={value}>
              {labelOf(value)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function LeaderboardPage({ problem, level, board, query, card }: LeaderboardPageProps) {
  const t = useTranslations("leaderboard.page");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [shown, show] = useOptimistic(query);
  const { explain } = useOrderWords(board.order);
  const problemHref = problemHrefOf(problem.slug);

  const change = (changes: Partial<BoardQuery>) =>
    startTransition(() => {
      const next = { ...query, ...changes, page: 1, around: false };
      show(next);
      router.replace(leaderboardHref(problem.slug, next), { scroll: false });
    });

  const pages = Math.ceil(board.total / board.per_page);
  const from = (board.page - 1) * board.per_page + 1;
  const to = from + board.items.length - 1;
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-title-1">{t("title")}</h1>
          <p className="flex flex-wrap items-center gap-2 text-mu">
            <Link href={problemHref} className="hover:text-tx hover:underline">
              {problem.title}
            </Link>
            {level !== null && <DifficultyBadge difficulty={level.difficulty} rank={level.rank} />}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ShareButton card={card} href={problemHref} />
          <Button asChild>
            <Link href={problemHref}>
              {t("openProblem")}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </header>
      <Cards problem={problem} board={board} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="flex max-w-[860px] min-w-[280px] flex-1 gap-2 text-caption text-mu">
          <Info size={14} aria-hidden="true" className="mt-0.5 flex-none" />
          <span>{explain}</span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex h-[30px] cursor-pointer items-center gap-2 rounded-md border border-bc bg-sf px-2.5 text-[12.5px]">
            <Checkbox
              checked={shown.group}
              onCheckedChange={(checked) => change({ group: checked === true })}
            />
            {t("group")}
          </label>
          {board.total > 0 && (
            <SortMenu board={board} sort={shown.sort} onSort={(sort) => change({ sort })} />
          )}
          {board.me !== null && (
            <Button asChild>
              <Link href={`${leaderboardHref(problem.slug, { ...query, around: true })}#me`}>
                {t("toMe")}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          )}
        </div>
      </div>
      {board.total === 0 ? (
        <PageState
          icon={Trophy}
          title={t("emptyTitle")}
          description={t("empty")}
          className="rounded-md border border-bd"
          actions={
            <Button asChild variant="primary">
              <Link href={problemHref}>{t("solve")}</Link>
            </Button>
          }
        />
      ) : (
        <>
          <BoardTable problem={problem} board={board} query={query} busy={busy} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-mu">
            <span>
              {board.items.length > 0 &&
                t.rich("shown", {
                  from,
                  to,
                  total: board.total,
                  n: (chunks) => <span className="font-mono text-tx">{chunks}</span>,
                })}
            </span>
            <Pagination
              page={board.page}
              count={pages}
              href={(page) => leaderboardHref(problem.slug, { ...query, page, around: false })}
            />
          </div>
        </>
      )}
    </div>
  );
}
