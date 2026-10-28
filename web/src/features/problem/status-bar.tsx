"use client";

// The status bar of the problem page (specs/08 §2, mock-up Bench): the mode, the level and the
// autosave on the left, the language and the cursor on the right. A slot of the layout, under the
// whole window; the editor publishes the cursor and the autosave through editor-status.
import { LoaderCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { useEditorStatus } from "./editor-status";

function Bar({ children }: { children: ReactNode }) {
  const t = useTranslations("problem.status");
  return (
    <footer
      aria-label={t("label")}
      className="hidden h-6 flex-none items-center gap-4 bg-ac px-3 font-mono text-[11px] text-acx sm:flex"
    >
      {children}
    </footer>
  );
}

export function ProblemStatusBar({ level, language }: { level: string; language: string }) {
  const t = useTranslations("problem.status");
  const locale = useLocale();
  const status = useEditorStatus();
  // The time of this browser, not of the server: the bar is drawn only here.
  const saved =
    status?.savedAt == null
      ? null
      : new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(
          new Date(status.savedAt),
        );
  return (
    <Bar>
      <span>{t("mode")}</span>
      <span>{level}</span>
      {saved !== null && <span>{t("saved", { time: saved })}</span>}
      <span className="flex-1" />
      <span>{language}</span>
      {status !== null && <span>{t("cursor", { line: status.line, column: status.column })}</span>}
    </Bar>
  );
}

export function LoadingStatusBar() {
  const t = useTranslations("problem.status");
  return (
    <Bar>
      <span className="flex items-center gap-2.5" role="status">
        <LoaderCircle size={11} className="animate-spin" aria-hidden="true" />
        {t("loading")}
      </span>
    </Bar>
  );
}
