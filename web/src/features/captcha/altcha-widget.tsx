"use client";

// The ALTCHA widget (ADR-0010): a web component that fetches a challenge from the API, finds its
// number in workers and gives the solution to send as `captcha`. Loaded on demand: only a captcha
// needs it. Its strings come from the messages, its colours from the tokens.
import type { CSSVariables } from "altcha/types";
import type {} from "altcha/types/react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";

const STYLE: Partial<CSSVariables> = {
  "--altcha-max-width": "100%",
  "--altcha-padding": "16px",
  "--altcha-border-color": "var(--bd)",
  "--altcha-border-radius": "var(--r-lg)",
  "--altcha-color-base": "var(--ed)",
  "--altcha-color-base-content": "var(--tx)",
  "--altcha-color-neutral": "var(--bc)",
  "--altcha-color-neutral-content": "var(--mu)",
  "--altcha-color-primary": "var(--ac)",
  "--altcha-color-primary-content": "var(--acx)",
  "--altcha-color-error": "var(--er)",
  "--altcha-color-error-content": "var(--sf)",
  "--altcha-color-success": "var(--ok)",
  "--altcha-color-success-content": "var(--sf)",
  "--altcha-checkbox-border-color": "var(--bc)",
  "--altcha-checkbox-border-radius": "var(--r-md)",
  "--altcha-checkbox-outline": "2px solid var(--ac)",
  "--altcha-input-background-color": "var(--ed)",
  "--altcha-spinner-color": "var(--ac)",
};

// The strings of the widget, its HTML as it is (the footer links to ALTCHA).
const STRINGS = [
  "ariaLinkLabel",
  "cancel",
  "enterCode",
  "enterCodeAria",
  "enterCodeFromImage",
  "error",
  "expired",
  "footer",
  "getAudioChallenge",
  "label",
  "loading",
  "reload",
  "verify",
  "verificationRequired",
  "verified",
  "verifying",
  "waitAlert",
] as const;

export interface AltchaWidgetProps {
  /** Where to fetch a challenge. */
  challengeUrl: string;
  /** The solution once the challenge is solved; null again when it expires or fails. */
  onChange: (solution: string | null) => void;
}

export function AltchaWidget({ challengeUrl, onChange }: AltchaWidgetProps) {
  const t = useTranslations("captcha");
  const locale = useLocale();
  const ref = useRef<HTMLElement>(null);
  const [loaded, setLoaded] = useState<boolean | "failed">(false);
  const change = useEffectEvent(onChange);
  // Before the element upgrades: it reads the strings of its language once.
  const prepare = useEffectEvent(() => {
    const strings = Object.fromEntries(STRINGS.map((key) => [key, t.raw(`widget.${key}`)]));
    globalThis.$altcha.i18n.set(locale, strings as Record<string, string>);
  });

  useEffect(() => {
    let alive = true;
    import("altcha").then(
      () => {
        if (!alive) return;
        prepare();
        setLoaded(true);
      },
      () => {
        if (alive) setLoaded("failed");
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    const listener = (event: Event) => {
      const { state, payload } = (event as CustomEvent<{ state: string; payload?: string }>).detail;
      change(state === "verified" && payload ? payload : null);
    };
    element.addEventListener("statechange", listener);
    return () => element.removeEventListener("statechange", listener);
  }, [loaded]);

  if (loaded === "failed") return <p className="text-er">{t("loadFailed")}</p>;
  if (!loaded) return <Skeleton className="h-[58px] w-full rounded-lg" />;
  return (
    <altcha-widget
      ref={ref}
      challenge={challengeUrl}
      language={locale}
      type="checkbox"
      style={STYLE}
    />
  );
}
