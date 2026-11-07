"use client";

// The public profile (FR-USR-04, mock-up Profile): the nick and the date of the account; the
// place and the points in the global leaderboard with the shift for a week, solved problems and
// the share of accepted Submits; solved problems by level and the list of them; the places held in
// the leaderboards of problems and the public solutions. The streak and the activity of the
// mock-up arrive with phase 4; the avatar shows the initials: the pictures of GitHub would tell it
// who looks at the profile.
import { ArrowRight, Share2 } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import {
  DifficultyBadge,
  difficultyTone,
  findDifficulty,
} from "@/components/domain/difficulty-badge";
import { WeekShift } from "@/components/domain/week-shift";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { useAccount } from "@/features/account/session";
import { useMetricWords } from "@/features/leaderboard/metrics";
import { leaderboardHref } from "@/features/leaderboard/query";
import type { Schemas } from "@/lib/api/client";
import { shareLink } from "@/lib/share";
import { cn } from "@/lib/utils";

import { profileHref, userSolutionsHref } from "./href";
import type { ProfileData } from "./load";
import { SolutionItem } from "./solution-item";

/** Solved problems listed before «Все N». */
export const SOLVED_SHOWN = 8;

function Card({
  title,
  action,
  className,
  children,
}: {
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className={cn("flex flex-col gap-3 rounded-md border border-bd bg-sf px-4 py-3.5", className)}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-label text-mu uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const linkClass =
  "inline-flex cursor-pointer items-center gap-1 text-caption text-ac underline-offset-2 hover:underline";

function Tile({ label, value, caption }: { label: string; value: ReactNode; caption: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-bd bg-sf px-4 py-3.5">
      <span className="font-mono text-label text-mu uppercase">{label}</span>
      <span className="text-metric">{value}</span>
      <span className="flex flex-wrap gap-x-2 text-caption text-mu">{caption}</span>
    </div>
  );
}

export function ProfileView({ profile, levels, solutions }: ProfileData) {
  const t = useTranslations("profile");
  const format = useFormatter();
  const me = useAccount();
  const own = me?.nick === profile.nick;
  const solved = profile.progress.reduce((sum, level) => sum + level.solved, 0);
  const total = profile.progress.reduce((sum, level) => sum + level.total, 0);
  const since = format.dateTime(new Date(profile.created_at), { dateStyle: "long" });
  const { rating, submits } = profile;

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-4 sm:px-8 sm:pt-6">
      <header className="flex flex-wrap items-center gap-4">
        <Avatar
          name={profile.display_name ?? profile.nick}
          size={64}
          className="rounded-md border-ac bg-acs text-ac"
        />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="truncate text-title-1">{profile.nick}</h1>
          <p className="text-mu">
            {profile.display_name !== null && (
              <>
                <span className="text-tx">{profile.display_name}</span>
                {" · "}
              </>
            )}
            {t("since", { date: since })}
            {own && ` · ${t("ownNote")}`}
          </p>
        </div>
        <ShareButton nick={profile.nick} />
      </header>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        <Tile
          label={t("place.label")}
          value={rating === null ? "—" : format.number(rating.rank)}
          caption={
            rating === null ? (
              t("place.none")
            ) : (
              <>
                <span>{t("place.of", { total: rating.total })}</span>
                <WeekShift delta={rating.week_delta} />
              </>
            )
          }
        />
        <Tile
          label={t("points.label")}
          value={format.number(rating?.points ?? 0)}
          caption={t("points.hint")}
        />
        <Tile label={t("solved.label")} value={solved} caption={t("solved.of", { total })} />
        <Tile
          label={t("accepted.label")}
          value={
            submits.total === 0
              ? "—"
              : format.number(submits.accepted / submits.total, { style: "percent" })
          }
          caption={
            submits.total === 0
              ? t("accepted.none")
              : t("accepted.of", { accepted: submits.accepted, total: submits.total })
          }
        />
      </div>

      <Levels levels={levels} progress={profile.progress} />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <Solved levels={levels} solved={profile.solved} own={own} />
        <BestPlaces places={profile.best_places} own={own} />
        <Solutions nick={profile.nick} solutions={solutions} total={profile.solutions} own={own} />
      </div>
    </div>
  );
}

/** «каталога» in the empty states of the own profile. */
const catalogue = (chunks: ReactNode) => (
  <Link href="/problems" className="text-ac underline-offset-2 hover:underline">
    {chunks}
  </Link>
);

function BestPlaces({ places, own }: { places: Schemas["BestPlace"][]; own: boolean }) {
  const t = useTranslations("profile.places");
  const words = useMetricWords();
  return (
    <Card title={t("title")}>
      {places.length === 0 ? (
        <p className="text-mu">{own ? t.rich("emptyOwn", { link: catalogue }) : t("empty")}</p>
      ) : (
        <ul className="-my-1">
          {places.map((place) => {
            const [main] = place.order;
            return (
              <li
                key={place.problem.slug}
                className="flex items-center gap-4 border-t border-bd py-2.5 first:border-t-0"
              >
                <span className="w-[76px] flex-none font-mono text-mu tabular-nums">
                  {t.rich("rank", {
                    rank: place.rank,
                    entries: place.entries,
                    n: (chunks) => (
                      <span className={cn("text-tx", place.rank <= 3 && "font-semibold")}>
                        {chunks}
                      </span>
                    ),
                  })}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <Link
                    href={leaderboardHref(place.problem.slug)}
                    className="truncate font-medium hover:text-ac"
                  >
                    {place.problem.title}
                  </Link>
                  {main !== undefined && (
                    <span className="truncate text-caption text-mu">
                      {t("by", { metric: words.name(main.metric) })}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function Solutions({
  nick,
  solutions,
  total,
  own,
}: {
  nick: string;
  solutions: Schemas["SolutionSummary"][];
  total: number;
  own: boolean;
}) {
  const t = useTranslations("profile.solutions");
  return (
    <Card
      title={t("title")}
      action={
        total > solutions.length && (
          <Link href={userSolutionsHref(nick)} className={linkClass}>
            {t("all", { count: total })}
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
        )
      }
    >
      {solutions.length === 0 ? (
        <p className="text-mu">{own ? t.rich("emptyOwn", { link: catalogue }) : t("empty")}</p>
      ) : (
        <ul className="-my-1">
          {solutions.map((item) => (
            <SolutionItem key={item.id} item={item} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ShareButton({ nick }: { nick: string }) {
  const t = useTranslations("profile.share");
  const share = async () => {
    const shared = await shareLink(nick, `${window.location.origin}${profileHref(nick)}`);
    if (shared === "copied") notify({ tone: "ok", title: t("copied") });
    if (shared === "failed") notify({ tone: "er", title: t("failed") });
  };
  return (
    <Button onClick={() => void share()} className="max-sm:w-full">
      <Share2 aria-hidden="true" />
      {t("button")}
    </Button>
  );
}

function Levels({
  levels,
  progress,
}: {
  levels: Schemas["Difficulty"][];
  progress: Schemas["DifficultyProgress"][];
}) {
  const t = useTranslations("profile.levels");
  return (
    <Card title={t("title")}>
      <ul className="flex flex-col gap-4">
        {progress.map((item) => {
          const level = findDifficulty(levels, item.difficulty);
          if (level === undefined) return null;
          const { solved, total } = item;
          return (
            <li key={item.difficulty} className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <DifficultyBadge {...level} />
                <span className="font-mono text-caption text-mu">
                  {t.rich("solved", {
                    solved,
                    total,
                    n: (chunks) => <span className="font-medium text-tx">{chunks}</span>,
                  })}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={t("bar", { level: level.difficulty.title, solved, total })}
                aria-valuemin={0}
                aria-valuemax={total}
                aria-valuenow={solved}
                className="h-1.5 rounded-md border border-bd bg-sf2"
              >
                <div
                  className={cn(
                    "h-full rounded-md",
                    difficultyTone(level.difficulty.token),
                    "bg-current",
                  )}
                  style={{ width: total === 0 ? 0 : `${(solved / total) * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** "21 окт.", "21 окт. 2025 г.": the year only when it is not the current one. */
function useDay(): (iso: string) => string {
  const format = useFormatter();
  const now = useNow();
  const year = (at: Date) => format.dateTime(at, { year: "numeric" });
  return (iso) => {
    const at = new Date(iso);
    return format.dateTime(at, {
      day: "numeric",
      month: "short",
      ...(year(at) !== year(now) && { year: "numeric" }),
    });
  };
}

function Solved({
  levels,
  solved,
  own,
}: {
  levels: Schemas["Difficulty"][];
  solved: Schemas["SolvedProblem"][];
  own: boolean;
}) {
  const t = useTranslations("profile.list");
  const day = useDay();
  const [all, setAll] = useState(false);
  const shown = all ? solved : solved.slice(0, SOLVED_SHOWN);
  const more = solved.length > SOLVED_SHOWN && !all;
  return (
    <Card
      title={t("title")}
      action={
        more && (
          <button type="button" onClick={() => setAll(true)} className={linkClass}>
            {t("all", { count: solved.length })}
            <ArrowRight size={12} aria-hidden="true" />
          </button>
        )
      }
    >
      {solved.length === 0 ? (
        <p className="text-mu">{own ? t.rich("emptyOwn", { link: catalogue }) : t("empty")}</p>
      ) : (
        <ul className="-my-1">
          {shown.map((problem) => {
            const level = findDifficulty(levels, problem.difficulty);
            return (
              <li
                key={problem.slug}
                className="flex items-center gap-3 border-t border-bd py-2.5 first:border-t-0"
              >
                <Link
                  href={`/problems/${problem.slug}`}
                  className="min-w-0 flex-1 truncate font-medium hover:text-ac"
                >
                  {problem.title}
                </Link>
                {level !== undefined && <DifficultyBadge {...level} compact />}
                <time
                  dateTime={problem.solved_at}
                  className="w-20 flex-none text-right font-mono text-caption text-mu"
                >
                  {day(problem.solved_at)}
                </time>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
