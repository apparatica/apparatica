"use client";

// The results panel of a problem page. Before the first check it explains Run and Submit (mock-up
// BenchEmpty); a check shows its status and can be cancelled. The pipeline, the banners and the
// result tabs replace the status line in T1.15a–T1.17.
import { SquareTerminal } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { VerdictBadge } from "@/components/domain/verdict-badge";
import { Button } from "@/components/ui/button";
import { Shortcut } from "@/components/ui/kbd";
import { isFinished } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";

import { ResultsSkeleton } from "./skeletons";
import { RUN_KEYS, SUBMIT_KEYS } from "./shortcuts";

const strong = (chunks: ReactNode) => <strong className="font-medium text-tx">{chunks}</strong>;

export function ResultsPanel({ submission }: { submission: SubmissionState }) {
  const t = useTranslations("problem.results");
  const { check } = submission;
  return (
    <section aria-label={t("label")} className="flex h-full min-h-0 flex-col bg-sf">
      {check === null ? (
        submission.restoring ? (
          <ResultsSkeleton />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2.5 bg-ed px-10 text-center">
            <SquareTerminal size={22} className="text-mu" aria-hidden="true" />
            <h2 className="text-[14px] font-medium">{t("emptyTitle")}</h2>
            <p className="max-w-[420px] text-mu">{t.rich("emptyDescription", { b: strong })}</p>
            <p className="flex gap-4 text-caption text-mu">
              <span>
                <Shortcut keys={RUN_KEYS} /> {t("runShortcut")}
              </span>
              <span>
                <Shortcut keys={SUBMIT_KEYS} /> {t("submitShortcut")}
              </span>
            </p>
          </div>
        )
      ) : (
        <div className="flex items-center gap-3 px-3.5 py-3" aria-live="polite">
          <VerdictBadge status={check.status} position={check.queue?.position} />
          {!isFinished(check) && (
            <Button loading={submission.cancelling} onClick={submission.cancel}>
              {t("cancel")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
