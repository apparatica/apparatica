"use client";

// Rows of a leaderboard (components.md, sheet CmpC; mock-ups SolutionLB, LeftTabsA): 34 px rows
// of a table — the place, the author and the metrics. Prize places 1–3 are bolder; the main
// metric of the order is bold and tinted; the own row has the --acs fill, a 3 px --ac bar on the
// left and the chip «вы». Later solutions with the same syntax tree fold under the row of the
// earliest one («×N совпадающих», FR-LB-04) and unfold into 28 px rows on --sf2. Between two
// blocks of rows — the gap «· · ·»; without an own place — «вашего места пока нет». A chevron at the
// end of a row opens the solution. Phones (narrower than 640 px) hide the `wide` columns and the
// date, and make the rows and the chevron 44 px for a finger.
import { ChevronDown, ChevronRight, CornerDownRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Avatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

export interface LeaderboardCell {
  key: string;
  /** The formatted value; "—" if the solution has no such metric. */
  text: string;
  /** Shown after the value, small: the unit in rows without a header. */
  unit?: string | null | undefined;
  /** The main metric of the order. */
  primary?: boolean | undefined;
  /** Shown from 640 px: phones hide the column. */
  wide?: boolean | undefined;
}

export interface LeaderboardAuthor {
  nick: string;
  /** The profile; without it the nick is text. */
  href?: string | null | undefined;
}

export interface LeaderboardRowProps {
  /** Equal metrics share a place (1, 2, 2, 4). */
  rank: number;
  author: LeaderboardAuthor;
  cells: readonly LeaderboardCell[];
  /** The date column, formatted; the column is absent when undefined, hidden on phones. */
  date?: string | undefined;
  /** The entry of the signed-in user. */
  me?: boolean | undefined;
  /** Later solutions with the same syntax tree folded under this one. */
  duplicates?: number | undefined;
  expanded?: boolean | undefined;
  /** Folds and unfolds the duplicates; without it the counter is a label. */
  onToggle?: (() => void) | undefined;
  /** The row is a later duplicate: the author of the solution that holds the place. */
  duplicateOf?: string | null | undefined;
  /** The id of the row element: «К моей строке» scrolls to it. */
  id?: string | undefined;
  /** The page of the solution: a chevron at the end of the row. */
  href?: string | undefined;
}

const PRIZES = 3;
const cell = "px-2 first:pl-3.5 last:pr-3.5";
/** The classes of a column header or cell that phones hide. */
export const WIDE = "max-sm:hidden";

function AuthorCell({ author, children }: { author: LeaderboardAuthor; children?: ReactNode }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Avatar name={author.nick} size={20} className="rounded-sm" />
      {author.href == null ? (
        <span className="truncate">{author.nick}</span>
      ) : (
        <Link href={author.href} className="truncate hover:text-ac hover:underline">
          {author.nick}
        </Link>
      )}
      {children}
    </span>
  );
}

/** The chevron to the solution of a row: the last cell. */
function SolutionLink({ href, nick }: { href: string | undefined; nick: string }) {
  const t = useTranslations("domain.leaderboard");
  if (href === undefined) return null;
  return (
    <td className="w-8 pr-2 text-right max-sm:w-11 max-sm:pr-0">
      <Link
        href={href}
        aria-label={t("open", { nick })}
        className="inline-flex size-6 items-center justify-center rounded-sm align-middle text-mu hover:bg-sf2 hover:text-tx max-sm:size-11"
      >
        <ChevronRight size={14} aria-hidden="true" />
      </Link>
    </td>
  );
}

function Value({ value, prize }: { value: LeaderboardCell; prize: boolean }) {
  return (
    <td
      className={cn(
        cell,
        "text-right font-mono whitespace-nowrap tabular-nums",
        value.wide && WIDE,
      )}
      data-primary={value.primary || undefined}
    >
      <span
        className={cn(
          value.primary && "rounded-sm bg-acs px-1.5 py-0.5 font-medium",
          value.primary && prize && "font-semibold",
        )}
      >
        {value.text}
      </span>
      {value.unit != null && (
        <span className="ml-1 text-[11px] text-mu normal-case">{value.unit}</span>
      )}
    </td>
  );
}

export function LeaderboardRow({
  rank,
  author,
  cells,
  date,
  me = false,
  duplicates = 0,
  expanded = false,
  onToggle,
  duplicateOf = null,
  id,
  href,
}: LeaderboardRowProps) {
  const t = useTranslations("domain.leaderboard");
  const prize = rank <= PRIZES;
  const counter = t("duplicates", { count: duplicates });
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <tr
      id={id}
      data-me={me || undefined}
      data-prize={prize || undefined}
      className={cn(
        "h-[34px] scroll-mt-24 border-t border-bd first:border-t-0 max-sm:h-11",
        me ? "bg-acs" : "hover:bg-sf2",
      )}
    >
      <th
        scope="row"
        className={cn(
          cell,
          "relative w-12 text-left font-mono font-normal tabular-nums",
          prize && "font-semibold",
        )}
      >
        {me && <span aria-hidden="true" className="absolute inset-y-0 left-0 w-[3px] bg-ac" />}
        {rank}
      </th>
      <td className={cn(cell, "w-full max-w-0")}>
        <AuthorCell author={author}>
          {me && (
            <span className="flex-none rounded-sm border border-ac px-1 font-mono text-[10px] leading-4 text-ac">
              {t("me")}
            </span>
          )}
          {duplicates > 0 &&
            (onToggle === undefined ? (
              <span className="flex-none rounded-sm border border-bc px-1.5 font-mono text-[11px] leading-[18px] text-mu">
                {counter}
              </span>
            ) : (
              <button
                type="button"
                aria-expanded={expanded}
                onClick={onToggle}
                className="inline-flex flex-none cursor-pointer items-center gap-1 rounded-sm border border-bc px-1.5 font-mono text-[11px] leading-[18px] text-mu hover:bg-sf2 hover:text-tx"
              >
                <Chevron size={12} aria-hidden="true" />
                {counter}
              </button>
            ))}
          {duplicateOf !== null && (
            <span className="truncate text-caption text-mu">
              {t("sameAs", { nick: duplicateOf })}
            </span>
          )}
        </AuthorCell>
      </td>
      {cells.map((value) => (
        <Value key={value.key} value={value} prize={prize} />
      ))}
      {date !== undefined && (
        <td className={cn(cell, "text-right text-caption whitespace-nowrap text-mu", WIDE)}>
          {date}
        </td>
      )}
      <SolutionLink href={href} nick={author.nick} />
    </tr>
  );
}

export interface LeaderboardMemberProps {
  /** The author of the later solution. */
  author: LeaderboardAuthor;
  /** The author of the solution that holds the place. */
  leader: string;
  /** The metrics of the group: the same as the leader's. */
  cells: readonly LeaderboardCell[];
  date?: string | undefined;
  /** The page of the solution. */
  href?: string | undefined;
}

/** A later solution with the same syntax tree, unfolded under the row that holds the place. */
export function LeaderboardMember({ author, leader, cells, date, href }: LeaderboardMemberProps) {
  const t = useTranslations("domain.leaderboard");
  return (
    <tr data-member="" className="h-7 border-t border-bd bg-sf2 text-mu max-sm:h-11">
      <td className={cell} />
      <td className={cn(cell, "w-full max-w-0")}>
        <span className="flex min-w-0 items-center gap-2">
          <CornerDownRight size={14} aria-hidden="true" className="flex-none" />
          <AuthorCell author={author}>
            <span className="truncate text-caption">{t("sameAs", { nick: leader })}</span>
          </AuthorCell>
        </span>
      </td>
      {cells.map((value) => (
        <td
          key={value.key}
          className={cn(
            cell,
            "text-right font-mono whitespace-nowrap tabular-nums",
            value.wide && WIDE,
          )}
        >
          {value.text}
          {value.unit != null && <span className="ml-1 text-[11px]">{value.unit}</span>}
        </td>
      ))}
      {date !== undefined && (
        <td className={cn(cell, "text-right text-caption whitespace-nowrap", WIDE)}>{date}</td>
      )}
      <SolutionLink href={href} nick={author.nick} />
    </tr>
  );
}

/** The gap «· · ·» between the top of a leaderboard and the own row. */
export function LeaderboardGap({ columns }: { columns: number }) {
  const t = useTranslations("domain.leaderboard");
  return (
    <tr data-gap="" className="h-7 border-t border-bd">
      <td colSpan={columns} className="text-center font-mono text-mu">
        <span aria-hidden="true">· · ·</span>
        <span className="sr-only">{t("gap")}</span>
      </td>
    </tr>
  );
}

/** The own row when the signed-in user has no place; `children` replaces the default words. */
export function LeaderboardNoPlace({
  columns,
  children,
}: {
  columns: number;
  children?: ReactNode;
}) {
  const t = useTranslations("domain.leaderboard");
  return (
    <tr data-no-place="" className="h-[34px] border-t border-bd">
      <td className={cn(cell, "w-12 font-mono text-mu")} aria-hidden="true">
        —
      </td>
      <td colSpan={columns - 1} className={cell}>
        {children ?? t("noPlace")}
      </td>
    </tr>
  );
}
