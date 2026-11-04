"use client";

// The public profile (FR-USR-04, mock-up Profile): the nick, the date of the account, solved
// problems by level and the list of them. The places, points, acceptance and streak of the mock-up
// arrive with the leaderboards (Ф3) and the activity (Ф4), and the avatar shows the initials: the
// pictures of GitHub would tell it who looks at the profile.
import { ArrowRight, Share2 } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import {
  DifficultyBadge,
  difficultyTone,
  findDifficulty,
} from "@/components/domain/difficulty-badge";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { useAccount } from "@/features/account/session";
import type { Schemas } from "@/lib/api/client";
import { shareLink } from "@/lib/share";
import { cn } from "@/lib/utils";

import { profileHref } from "./href";
import type { ProfileData } from "./load";

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

export function ProfileView({ profile, levels }: ProfileData) {
  const t = useTranslations("profile");
  const format = useFormatter();
  const me = useAccount();
  const own = me?.nick === profile.nick;
  const solved = profile.progress.reduce((sum, level) => sum + level.solved, 0);
  const total = profile.progress.reduce((sum, level) => sum + level.total, 0);
  const since = format.dateTime(new Date(profile.created_at), { dateStyle: "long" });

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

      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(200px,100%),1fr))] gap-2">
        <div className="flex flex-col gap-1 rounded-md border border-bd bg-sf px-4 py-3.5">
          <span className="font-mono text-label text-mu uppercase">{t("solved.label")}</span>
          <span className="text-metric">{solved}</span>
          <span className="text-caption text-mu">{t("solved.of", { total })}</span>
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Levels levels={levels} progress={profile.progress} />
        <Solved levels={levels} solved={profile.solved} own={own} />
      </div>
    </div>
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
          <button
            type="button"
            onClick={() => setAll(true)}
            className="inline-flex cursor-pointer items-center gap-1 text-caption text-ac underline-offset-2 hover:underline"
          >
            {t("all", { count: solved.length })}
            <ArrowRight size={12} aria-hidden="true" />
          </button>
        )
      }
    >
      {solved.length === 0 ? (
        <p className="text-mu">
          {own
            ? t.rich("emptyOwn", {
                link: (chunks) => (
                  <Link href="/problems" className="text-ac underline-offset-2 hover:underline">
                    {chunks}
                  </Link>
                ),
              })
            : t("empty")}
        </p>
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
