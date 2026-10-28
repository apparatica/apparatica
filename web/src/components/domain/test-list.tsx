"use client";

// The list of tests (components.md, sheets CmpB and ResultTabs): a row is a status icon, the name
// and a caption, on the right the time or the cycle of a failure. Passed (`circle-check`, --ok),
// running (`loader-circle`, --in), failed (`circle-x`, --er, the row on --ers), not run
// (`circle-minus`, --mu); hidden tests have a lock in the tone of their status. A failed test
// opens the table "signal @cycle / expected / actual" and the notes under it (FR-TST-02).
import {
  ChevronRight,
  CircleCheck,
  CircleMinus,
  CircleX,
  LoaderCircle,
  Lock,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { type ComponentProps, type ReactNode, useId, useState } from "react";

import { cn } from "@/lib/utils";

export type TestStatus = "passed" | "running" | "failed" | "notRun";

export interface TestMismatch {
  signal: string;
  cycle: number;
  expected: string;
  actual: string;
}

export interface TestRowView {
  key: string;
  status: TestStatus;
  /** Hidden tests: a lock in place of the status icon. */
  hidden?: boolean | undefined;
  /** "Тест 7 · push и pop одновременно", "Тесты 1–6", "Скрытые тесты · 20". */
  title: string;
  /** The status in words, or the names of the folded tests. */
  caption: string;
  /** Right: the time of passed tests, "такт 143" of a failed one. */
  aside?: string | undefined;
  /** Right: how many tests a folded row holds. */
  count?: number | undefined;
  /** A failed test: the row opens them, open at first. */
  mismatches?: readonly TestMismatch[] | undefined;
  /** Under the mismatches: the seed, the hints of the author. */
  notes?: readonly string[] | undefined;
  /** Under the mismatches, before the notes: "Показать на диаграмме". */
  action?: ReactNode;
}

export interface TestListProps extends ComponentProps<"section"> {
  /** "Открытые тесты · Run". */
  title: string;
  /** Right of the title: "первое расхождение останавливает прогон". */
  caption?: string | undefined;
  rows: readonly TestRowView[];
}

const STATUSES: Record<TestStatus, { icon: LucideIcon; tone: string }> = {
  passed: { icon: CircleCheck, tone: "text-ok" },
  running: { icon: LoaderCircle, tone: "text-in" },
  failed: { icon: CircleX, tone: "text-er" },
  notRun: { icon: CircleMinus, tone: "text-mu" },
};

function Mismatches({
  id,
  mismatches,
  notes,
  action,
}: {
  id: string;
  mismatches: readonly TestMismatch[];
  notes: readonly string[];
  action: ReactNode;
}) {
  const t = useTranslations("domain.tests");
  const lines = notes.map((note) => (
    <p key={note} className="text-caption text-mu">
      {note}
    </p>
  ));
  return (
    <div id={id} className="flex flex-col gap-2 pt-2 pr-3.5 pb-3 pl-[37px]">
      {mismatches.length > 0 && (
        <table className="w-full border-collapse border border-bc font-mono text-code">
          <thead>
            <tr className="border-b border-bd text-left text-label text-mu uppercase">
              <th scope="col" className="w-[30%] px-2.5 py-1.5 font-normal">
                {t("signal")}
              </th>
              <th scope="col" className="w-[35%] px-2.5 py-1.5 font-normal">
                {t("expected")}
              </th>
              <th scope="col" className="px-2.5 py-1.5 font-normal">
                {t("actual")}
              </th>
            </tr>
          </thead>
          <tbody>
            {mismatches.map(({ signal, cycle, expected, actual }) => (
              <tr key={`${signal}@${cycle}`} className="border-b border-bd last:border-b-0">
                <th scope="row" className="px-2.5 py-1 text-left font-normal text-mu">
                  {signal} @{cycle}
                </th>
                <td className="px-2.5 py-1">{expected}</td>
                <td className={cn("px-2.5 py-1", actual !== expected && "bg-ers text-er")}>
                  {actual}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {action == null ? (
        lines
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {action}
          {lines}
        </div>
      )}
    </div>
  );
}

function Row({ row }: { row: TestRowView }) {
  const t = useTranslations("domain.tests");
  const detailsId = useId();
  const [open, setOpen] = useState(true);
  const { icon, tone } = STATUSES[row.status];
  const Icon = row.hidden === true ? Lock : icon;
  const mismatches = row.mismatches ?? [];
  const notes = row.notes ?? [];
  const opens = mismatches.length > 0 || notes.length > 0 || row.action != null;

  const body = (
    <>
      <Icon
        size={15}
        role="img"
        aria-label={
          row.hidden === true
            ? t("hidden", { status: t(`status.${row.status}`) })
            : t(`status.${row.status}`)
        }
        className={cn(
          "flex-none",
          tone,
          row.status === "running" && row.hidden !== true && "animate-spin",
        )}
      />
      <span className="flex min-w-0 flex-1 flex-col leading-[1.3]">
        <span className="truncate text-[13px] font-medium text-tx">{row.title}</span>
        <span className="truncate text-caption text-mu" title={row.caption}>
          {row.caption}
        </span>
      </span>
      {row.aside !== undefined && (
        <span
          className={cn(
            "flex-none font-mono text-[11.5px]",
            row.status === "failed" ? "font-medium text-er" : "text-mu",
          )}
        >
          {row.aside}
        </span>
      )}
      {row.count !== undefined && (
        <span className="flex-none rounded-xs border border-bc px-1.5 font-mono text-[11px] text-mu">
          {row.count}
        </span>
      )}
    </>
  );

  return (
    <li
      data-status={row.status}
      className={cn("border-b border-bd last:border-b-0", row.status === "failed" && "bg-ers")}
    >
      {opens ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={detailsId}
          className="flex w-full cursor-pointer items-center gap-2.5 px-3.5 py-1.5 text-left focus-visible:-outline-offset-2"
          onClick={() => setOpen(!open)}
        >
          {body}
          <ChevronRight
            size={14}
            aria-hidden="true"
            className={cn("flex-none text-mu transition-transform", open && "rotate-90")}
          />
        </button>
      ) : (
        <div className="flex items-center gap-2.5 px-3.5 py-1.5">{body}</div>
      )}
      {opens && (
        <div hidden={!open} className="bg-sf">
          <Mismatches id={detailsId} mismatches={mismatches} notes={notes} action={row.action} />
        </div>
      )}
    </li>
  );
}

export function TestList({ title, caption, rows, className, ...props }: TestListProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={cn("flex flex-col", className)} {...props}>
      <div className="flex items-baseline justify-between gap-3 border-b border-bd px-3.5 py-2">
        <h3 id={headingId} className="font-mono text-label text-mu uppercase">
          {title}
        </h3>
        {caption !== undefined && <span className="text-caption text-mu">{caption}</span>}
      </div>
      <ul>
        {rows.map((row) => (
          <Row key={row.key} row={row} />
        ))}
      </ul>
    </section>
  );
}
