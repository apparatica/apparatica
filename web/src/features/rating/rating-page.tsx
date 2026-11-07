"use client";

// The global leaderboard of users (FR-LB-05, mock-up GlobalLB): the card «Ваша позиция» with the
// points missing to the next place, how points are counted (the formula of the API), the table —
// place, user, points, solved problems by level, all solved, the shift for a week — and pages.
// Off the page, the own row comes after the gap «· · ·» with up to two rows around it. No period
// switch and no search by nick (specs/08 §6).
import { ArrowRight, ChartColumn } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { DifficultyBadge } from "@/components/domain/difficulty-badge";
import { WeekShift } from "@/components/domain/week-shift";
import {
  type LeaderboardCell,
  LeaderboardGap,
  LeaderboardRow,
} from "@/components/domain/leaderboard-row";
import { PageState } from "@/components/domain/page-state";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { useGuest } from "@/features/account/session";
import { profileHref } from "@/features/profile/href";
import type { Schemas } from "@/lib/api/client";
import { loginHref } from "@/lib/session";

import { RATING_PATH, ratingHref } from "./query";

type Row = Schemas["RatingRow"];

export interface RatingPageProps {
  rating: Schemas["GlobalLeaderboard"];
  levels: Schemas["Difficulty"][];
}

const number = new Intl.NumberFormat("ru-RU");

/** The row just above the own one, wherever the page shows it. */
function rowAbove(rating: RatingPageProps["rating"], me: Row): Row | undefined {
  return [...rating.items, ...rating.around_me].find((row) => row.rank === me.rank - 1);
}

function MineCard({ rating }: { rating: RatingPageProps["rating"] }) {
  const t = useTranslations("rating.mine");
  const guest = useGuest();
  const { me } = rating;
  if (me === null) {
    return (
      <section
        aria-label={t("title")}
        className="rounded-md border border-bd bg-sf px-4 py-3 text-caption text-mu"
      >
        {guest
          ? t.rich("guest", {
              link: (chunks) => (
                <Link href={loginHref(RATING_PATH)} className="text-ac underline">
                  {chunks}
                </Link>
              ),
            })
          : t.rich("noPoints", {
              link: (chunks) => (
                <Link href="/problems" className="text-ac underline">
                  {chunks}
                </Link>
              ),
            })}
      </section>
    );
  }
  const above = rowAbove(rating, me);
  return (
    <section
      aria-label={t("title")}
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-md border border-ac bg-acs px-4 py-3"
    >
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <h2 className="font-mono text-label text-ac uppercase">{t("title")}</h2>
        <p className="flex items-baseline gap-1.5">
          <span className="font-mono text-[22px] leading-7 font-medium tabular-nums">
            {number.format(me.rank)}
          </span>
          <span className="text-caption text-mu">{t("place")}</span>
        </p>
        <p className="flex items-baseline gap-1.5">
          <span className="font-mono text-[22px] leading-7 font-medium tabular-nums">
            {number.format(me.points)}
          </span>
          <span className="text-caption text-mu">{t("points", { count: me.points })}</span>
        </p>
        <p className="text-caption">
          <WeekShift delta={me.week_delta} />
        </p>
      </div>
      <p className="text-caption">
        {me.rank === 1
          ? t("first")
          : above !== undefined &&
            t.rich("toNext", {
              rank: above.rank,
              count: above.points - me.points + 1,
              b: (chunks) => <b className="font-mono font-semibold">{chunks}</b>,
            })}
      </p>
    </section>
  );
}

function Formula({ rating, levels }: RatingPageProps) {
  const t = useTranslations("rating.formula");
  const { solved, places } = rating.formula;
  const perLevel = levels
    .map((level) => t("level", { level: level.title, count: solved[level.key] ?? 0 }))
    .join(", ");
  const perPlace = places
    .map((points, index) => t("place", { rank: index + 1, count: points }))
    .join(", ");
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-bd bg-sf px-4 py-3 text-caption">
      <p>{t("solved", { levels: perLevel })}</p>
      {places.length > 0 && <p>{t("places", { places: perPlace })}</p>}
      <p className="text-mu">{t("rules")}</p>
      <p className="text-mu">{t("version", { version: rating.formula.version })}</p>
    </div>
  );
}

function RatingTable({ rating, levels }: RatingPageProps) {
  const t = useTranslations("rating.table");
  const cells = (row: Row): LeaderboardCell[] => {
    const all = Object.values(row.solved).reduce((sum, count) => sum + count, 0);
    const delta = row.week_delta;
    return [
      { key: "points", text: number.format(row.points), primary: true },
      ...levels.map((level) => ({
        key: level.key,
        text: number.format(row.solved[level.key] ?? 0),
      })),
      { key: "solved", text: number.format(all) },
      {
        key: "week",
        text: delta === null || delta === 0 ? "—" : `${delta > 0 ? "↑" : "↓"} ${Math.abs(delta)}`,
      },
    ];
  };
  const rowOf = (row: Row) => (
    <LeaderboardRow
      key={row.rank}
      rank={row.rank}
      author={{ nick: row.user.nick, href: profileHref(row.user.nick) }}
      cells={cells(row)}
      me={row.is_me}
      id={row.is_me ? "me" : undefined}
    />
  );
  // The place, the user, the points, the levels, all solved and the week.
  const columns = levels.length + 5;
  const { items, around_me: around } = rating;
  const firstItem = items[0]?.rank ?? 0;
  const lastItem = items.at(-1)?.rank ?? 0;
  const before = around.filter((row) => row.rank < firstItem);
  const after = around.filter((row) => row.rank > lastItem);
  const head = "px-2 text-right font-normal";
  return (
    <div className="overflow-x-auto rounded-md border border-bd">
      <table aria-label={t("label")} className="w-full min-w-[720px] border-collapse text-[12.5px]">
        <thead>
          <tr className="h-[34px] border-b border-bd bg-sf2 text-left font-mono text-label whitespace-nowrap text-mu uppercase">
            <th scope="col" className="w-12 px-2 pl-3.5 font-normal">
              {t("rank")}
            </th>
            <th scope="col" className="px-2 font-normal">
              {t("user")}
            </th>
            <th scope="col" className={`${head} font-medium`}>
              {t("points")}
            </th>
            {levels.map((level, index) => (
              <th key={level.key} scope="col" className={head}>
                <DifficultyBadge difficulty={level} rank={index + 1} className="normal-case" />
              </th>
            ))}
            <th scope="col" className={head}>
              {t("solved")}
            </th>
            <th scope="col" className={`${head} pr-3.5`}>
              {t("week")}
            </th>
          </tr>
        </thead>
        <tbody>
          {before.map(rowOf)}
          {before.length > 0 && <LeaderboardGap columns={columns} />}
          {items.map(rowOf)}
          {after.length > 0 && (after[0]?.rank ?? 0) > lastItem + 1 && (
            <LeaderboardGap columns={columns} />
          )}
          {after.map(rowOf)}
        </tbody>
      </table>
    </div>
  );
}

export function RatingPage({ rating, levels }: RatingPageProps) {
  const t = useTranslations("rating");
  const [explained, explain] = useState(false);
  const formulaId = useId();
  const pages = Math.ceil(rating.total / rating.per_page);
  const from = (rating.page - 1) * rating.per_page + 1;
  const to = from + rating.items.length - 1;
  const around = rating.around_me;
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-title-1">{t("title")}</h1>
          <p className="text-mu">{t("subtitle", { count: rating.total })}</p>
        </div>
        <button
          type="button"
          aria-expanded={explained}
          aria-controls={formulaId}
          onClick={() => explain(!explained)}
          className="inline-flex cursor-pointer items-center gap-1 text-caption text-ac underline"
        >
          {t("formula.toggle")}
          <ArrowRight size={12} aria-hidden="true" />
        </button>
      </header>
      <div id={formulaId} hidden={!explained}>
        {explained && <Formula rating={rating} levels={levels} />}
      </div>
      <MineCard rating={rating} />
      {rating.total === 0 ? (
        <PageState
          icon={ChartColumn}
          title={t("emptyTitle")}
          description={t("empty")}
          className="rounded-md border border-bd"
          actions={
            <Button asChild variant="primary">
              <Link href="/problems">{t("solve")}</Link>
            </Button>
          }
        />
      ) : (
        <>
          {rating.me !== null && (
            <div className="flex justify-end">
              <Button asChild>
                <a href="#me">
                  {t("toMe")}
                  <ArrowRight aria-hidden="true" />
                </a>
              </Button>
            </div>
          )}
          <RatingTable rating={rating} levels={levels} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-mu">
            <span>
              {rating.items.length > 0 &&
                t.rich(around.length > 0 ? "shownAround" : "shown", {
                  from,
                  to,
                  aroundFrom: around[0]?.rank ?? 0,
                  aroundTo: around.at(-1)?.rank ?? 0,
                  total: rating.total,
                  n: (chunks) => <span className="font-mono text-tx">{chunks}</span>,
                })}
            </span>
            <Pagination page={rating.page} count={pages} href={ratingHref} />
          </div>
        </>
      )}
    </div>
  );
}
