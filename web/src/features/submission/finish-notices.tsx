"use client";

// The notices of checks that ended out of sight (FR-RUN-08): a notification with the verdict, and
// the verdict before the title of a hidden tab. Mounted once in the layout.
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { notify, type Tone } from "@/components/ui/toast";
import { prefixHiddenTitle } from "@/lib/tab-title";

import { onFinished } from "./finished";
import type { Status } from "./machine";

const TONES: Record<Status, Tone> = {
  accepted: "ok",
  accepted_with_warnings: "wn",
  limit_exceeded: "wn",
  wrong_answer: "er",
  compile_error: "er",
  forbidden_construct: "er",
  internal_error: "er",
  cancelled: "in",
  queued: "in",
  running: "in",
};

// Long enough to be read after coming back; Sonner holds it while the tab is hidden.
const NOTICE_MS = 10_000;

export function FinishNotices() {
  const t = useTranslations("problem.finished");
  const verdict = useTranslations("domain.verdict");
  const kind = useTranslations("domain.submissions.kind");

  useEffect(
    () =>
      onFinished((check, away) => {
        const label = verdict(check.status);
        notify({
          tone: TONES[check.status],
          title: label,
          description: t("caption", { kind: kind(check.kind), title: check.title }),
          action: away
            ? {
                label: t("open"),
                href: `/problems/${encodeURIComponent(check.problem)}?submission=${check.id}`,
              }
            : undefined,
          duration: NOTICE_MS,
        });
        prefixHiddenTitle(label);
      }),
    [t, verdict, kind],
  );
  return null;
}
