"use client";

// «Мои отправки» of a problem (FR-PRB-06, sheet LeftTabsA): newest first, a row is the status icon,
// the status in its colour, the short reason and the time, on the right the kind. The shown
// submission is on --acs; a submission the server no longer has is muted and does not open.
// Without `onOpen` (phones, which have no editor) the rows are plain text.
import { useFormatter, useNow, useTranslations } from "next-intl";
import type { ComponentProps } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { verdictMark, type VerdictStatus } from "./verdict-badge";

export interface SubmissionRowView {
  id: string;
  status: VerdictStatus;
  kind: "run" | "submit";
  /** "тест 7 из 32", "строка 16: expected ';'"; null: the status says it all. */
  reason: string | null;
  /** ISO 8601. */
  createdAt: string;
  /** Deleted by the server when its time ran out. */
  gone?: boolean | undefined;
}

export interface SubmissionListProps extends Omit<ComponentProps<"section">, "children"> {
  /** null: loading. */
  rows: readonly SubmissionRowView[] | null;
  /** The submission the results show. */
  selected?: string | null | undefined;
  onOpen?: ((id: string) => void) | undefined;
}

const DAY_MS = 86_400_000;

/** "сегодня, 14:32", "вчера, 09:10", "12 окт., 14:08", "12 окт. 2025 г., 14:08": days in the time
 * zone of the formatter. */
function useWhen(): (iso: string) => string {
  const t = useTranslations("domain.submissions");
  const format = useFormatter();
  const now = useNow();
  const day = (at: Date) =>
    format.dateTime(at, { year: "numeric", month: "numeric", day: "numeric" });
  const year = (at: Date) => format.dateTime(at, { year: "numeric" });
  return (iso) => {
    const at = new Date(iso);
    const time = format.dateTime(at, { hour: "2-digit", minute: "2-digit" });
    if (day(at) === day(now)) return t("today", { time });
    if (day(at) === day(new Date(now.getTime() - DAY_MS))) return t("yesterday", { time });
    const date = format.dateTime(at, {
      day: "numeric",
      month: "short",
      ...(year(at) !== year(now) && { year: "numeric" }),
    });
    return t("on", { date, time });
  };
}

function Row({
  row,
  selected,
  onOpen,
}: {
  row: SubmissionRowView;
  selected: boolean;
  onOpen: ((id: string) => void) | undefined;
}) {
  const t = useTranslations("domain");
  const when = useWhen();
  const { icon: Icon, tone } = verdictMark(row.status);
  const passedRun = row.kind === "run" && row.status === "accepted";
  const status = passedRun ? t("submissions.runPassed") : t(`verdict.${row.status}`);
  const reason = row.gone ? t("submissions.gone") : row.reason;
  const content = (
    <>
      <Icon
        size={16}
        aria-hidden="true"
        className={cn(
          "flex-none",
          row.gone ? "text-mu" : tone,
          row.status === "running" && "animate-spin",
        )}
      />
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate font-medium", row.gone ? "text-mu" : tone)}>
          {status}
        </span>
        <span className="block truncate text-caption text-mu">
          {reason === null ? when(row.createdAt) : `${reason} · ${when(row.createdAt)}`}
        </span>
      </span>
      <span className="flex-none rounded-sm px-1.5 py-px font-mono text-[11px] text-mu inset-ring inset-ring-bc">
        {t(`submissions.kind.${row.kind}`)}
      </span>
    </>
  );
  const look = "flex w-full items-center gap-3 px-3.5 py-2.5 text-left";
  return (
    <li className="border-b border-bd">
      {onOpen === undefined ? (
        <div className={look}>{content}</div>
      ) : (
        <button
          type="button"
          disabled={row.gone}
          aria-current={selected ? "true" : undefined}
          onClick={() => onOpen(row.id)}
          className={cn(
            look,
            "cursor-pointer outline-none hover:bg-sf2 focus-visible:inset-ring-2 focus-visible:inset-ring-ac disabled:cursor-default disabled:hover:bg-transparent",
            selected && "bg-acs hover:bg-acs",
          )}
        >
          {content}
        </button>
      )}
    </li>
  );
}

export function SubmissionList({
  rows,
  selected = null,
  onOpen,
  className,
  ...props
}: SubmissionListProps) {
  const t = useTranslations("domain.submissions");
  return (
    <section aria-label={t("title")} className={cn("flex flex-col", className)} {...props}>
      <header className="flex items-baseline justify-between gap-3 border-b border-bd px-3.5 py-2.5">
        <h3 className="font-mono text-label text-mu uppercase">{t("title")}</h3>
        <span className="text-caption text-mu">{t("order")}</span>
      </header>
      {rows === null ? (
        <ul aria-busy="true" aria-label={t("loading")}>
          {[0, 1, 2].map((key) => (
            <li key={key} className="flex items-center gap-3 border-b border-bd px-3.5 py-3">
              <Skeleton className="size-4 rounded-full" />
              <span className="flex flex-1 flex-col gap-1.5">
                <Skeleton className="h-3 w-32" />
                <Skeleton className="h-2.5 w-44" />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <ul>
          {rows.map((row) => (
            <Row key={row.id} row={row} selected={row.id === selected} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </section>
  );
}
