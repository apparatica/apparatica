"use client";

// The limits of a guest in the results panel (FR-GST-04, sheet Guest): the counter of the checks
// left this hour, and when they are spent, the wait until the next one. «Войти и продолжить» and
// the hint that signed-in users get more come with accounts (Ф2).
import { CalendarClock, Clock } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { formatCountdown } from "./limits";
import { Banner } from "./result-banner";

const timer = (chunks: ReactNode) => <span className="font-mono text-tx">{chunks}</span>;

/** «Проверок: 3 из 10 в час». */
export function QuotaCounter({ window }: { window: Schemas["QuotaWindow"] }) {
  const t = useTranslations("problem.results.limit");
  const spent = window.remaining === 0;
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1.5 rounded-sm border px-2 font-mono text-[11px] whitespace-nowrap normal-case",
        spent ? "border-wn text-wn" : "border-bd text-mu",
      )}
    >
      <CalendarClock size={12} aria-hidden="true" />
      {t("counter", { remaining: window.remaining, limit: window.limit })}
    </span>
  );
}

export interface LimitNoticeProps {
  /** The milliseconds until the next check. */
  left: number;
  /** In place of the banner of a check, or alone in the empty results panel. */
  layout: "banner" | "panel";
}

/** «Лимит проверок исчерпан» with the timer. The code stays in the editor: nothing to lose. */
export function LimitNotice({ left, layout }: LimitNoticeProps) {
  const t = useTranslations("problem.results.limit");
  const time = formatCountdown(left);
  const body = t.rich("spentBody", { time, timer });
  const wait = (
    <Button variant="outline" disabled>
      {t("runIn", { time })}
    </Button>
  );
  if (layout === "banner") {
    return (
      <Banner tone="wn" icon={Clock} title={t("spent")} actions={wait}>
        {body}
      </Banner>
    );
  }
  return (
    <div className="flex max-w-[460px] flex-col items-center gap-2.5 text-center">
      <Clock size={22} aria-hidden="true" className="text-wn" />
      <h2 className="text-[14px] font-medium">{t("spent")}</h2>
      <p className="text-mu">{body}</p>
      {wait}
    </div>
  );
}
