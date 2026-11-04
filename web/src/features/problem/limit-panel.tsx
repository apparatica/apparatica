"use client";

// The limits of checks in the results panel (FR-GST-04, sheet Guest): the counter of the checks
// left this hour, and when they are spent, the wait until the next one. A guest is also offered to
// log in: signed-in users get more checks. The login returns to this page; the code waits in the
// browser.
import { CalendarClock, Clock, Info } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useGuest } from "@/features/account/session";
import type { Schemas } from "@/lib/api/client";
import { formatCountdown } from "@/lib/clock";
import { loginHref } from "@/lib/session";
import { cn } from "@/lib/utils";

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

/** «Осталось 3 проверки из 10 в этот час. Вошедшим доступно больше. Войти →», for a guest. */
export function QuotaHint({ window }: { window: Schemas["QuotaWindow"] }) {
  const t = useTranslations("problem.results.limit");
  const path = usePathname();
  return (
    <p className="flex items-start gap-2.5 rounded-md border border-in bg-ins px-3.5 py-2.5">
      <Info size={14} aria-hidden="true" className="mt-[3px] flex-none text-in" />
      <span>
        {t("left", { remaining: window.remaining, limit: window.limit })}{" "}
        <Link href={loginHref(path)} className="text-in underline underline-offset-2">
          {t("leftLogin")}
        </Link>
      </span>
    </p>
  );
}

export interface LimitNoticeProps {
  /** The milliseconds until the next check. */
  left: number;
  /** In place of the banner of a check, or alone in the empty results panel. */
  layout: "banner" | "panel";
}

/** «Лимит проверок исчерпан» with the timer, and «Войти и продолжить» for a guest. The code stays
 * in the editor: nothing to lose. */
export function LimitNotice({ left, layout }: LimitNoticeProps) {
  const t = useTranslations("problem.results.limit");
  const guest = useGuest();
  const path = usePathname();
  const time = formatCountdown(left);
  const body = t.rich("spentBody", { time, timer });
  const wait = (
    <>
      {guest && (
        <Button variant="primary" asChild>
          <Link href={loginHref(path)}>{t("login")}</Link>
        </Button>
      )}
      <Button variant="outline" disabled>
        {t("runIn", { time })}
      </Button>
    </>
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
      <div className="flex flex-wrap justify-center gap-2">{wait}</div>
    </div>
  );
}
