"use client";

// «Мои отправки» of the problem page (FR-PRB-06, FR-GST-03, sheets LeftTabsA/B): the submissions of
// this browser for the problem, newest first. A click opens the code and the results of one; the
// empty state hints at Run and Submit. The shown check updates its own row; while another one is
// unfinished, the tab reads the list of the server every few seconds.
import { useQuery } from "@tanstack/react-query";
import { SquareTerminal } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { SubmissionList, type SubmissionRowView } from "@/components/domain/submission-list";
import { Shortcut } from "@/components/ui/kbd";
import type { LocalSubmission } from "@/features/guest/submissions";
import { submissionKeys, syncSubmissions } from "@/features/submission/api";

import type { BenchProblem } from "./bench";
import { RUN_KEYS, SUBMIT_KEYS } from "./shortcuts";
import { submissionReason } from "./submissions-view";

export interface SubmissionsTabProps {
  problem: Pick<BenchProblem, "slug" | "version" | "tests">;
  /** null: on the server and while the page hydrates. */
  submissions: readonly LocalSubmission[] | null;
  /** The submission the results show. */
  selected: string | null;
  onOpen: (id: string) => void;
}

const strong = (chunks: ReactNode) => <b className="font-medium text-tx">{chunks}</b>;
const SYNC_MS = 5000;

export function SubmissionsTab({ problem, submissions, selected, onOpen }: SubmissionsTabProps) {
  const t = useTranslations("problem.submissions");
  const waiting =
    submissions?.some(
      (item) =>
        (item.status === "queued" || item.status === "running") &&
        item.id !== selected &&
        !item.gone,
    ) ?? false;
  useQuery({
    queryKey: submissionKeys.list(problem.slug),
    queryFn: () => syncSubmissions(problem.slug),
    enabled: waiting,
    refetchInterval: SYNC_MS,
    gcTime: 0,
  });
  if (submissions !== null && submissions.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
        <SquareTerminal size={22} className="text-mu" aria-hidden="true" />
        <h2 className="text-[14px] font-medium">{t("emptyTitle")}</h2>
        <p className="max-w-[340px] text-mu">{t.rich("emptyDescription", { b: strong })}</p>
        <p className="flex gap-4 text-caption text-mu">
          <span>
            <Shortcut keys={RUN_KEYS} /> Run
          </span>
          <span>
            <Shortcut keys={SUBMIT_KEYS} /> Submit
          </span>
        </p>
      </div>
    );
  }

  const reasonOf = (submission: LocalSubmission): string | null => {
    const reason = submissionReason(submission, problem);
    switch (reason?.kind) {
      case undefined:
        return null;
      case "test":
        return reason.total === null
          ? t("reason.test", { number: reason.number })
          : t("reason.testOf", { number: reason.number, total: reason.total });
      case "hidden":
        return t("reason.hidden", { number: reason.number, total: reason.total });
      case "line":
        return t("reason.line", { line: reason.line, message: reason.message });
      case "message":
        return reason.message;
      case "limit":
        return t(`reason.limit.${reason.limit}`);
      case "warnings":
        return t("reason.warnings");
      case "codes":
        return t("reason.codes", { codes: reason.codes.join(", ") });
    }
  };
  const rows: SubmissionRowView[] | null =
    submissions?.map((submission) => ({
      id: submission.id,
      status: submission.status,
      kind: submission.kind,
      reason: reasonOf(submission),
      createdAt: submission.created_at,
      gone: submission.gone ?? false,
    })) ?? null;

  return (
    <div className="flex flex-col">
      <SubmissionList rows={rows} selected={selected} onOpen={onOpen} />
      <p className="px-3.5 py-3 text-caption text-mu">{t("note")}</p>
    </div>
  );
}
