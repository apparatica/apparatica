"use client";

// The problem page on phones has no editor (FR-MOB-02, mock-up MobTask): this block at the bottom
// offers to solve on a computer and to take the link there. Guests share it (Web Share) or copy it;
// a letter to oneself comes with accounts (Ф2, ОВ-15).
import { Copy, Monitor, Share2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";

const never = () => () => {};
const canShare = () => typeof navigator.share === "function";

/** The page without its tab and submission: the problem itself. */
const problemUrl = () => `${window.location.origin}${window.location.pathname}`;

export function DesktopOffer({ title }: { title: string }) {
  const t = useTranslations("problem.phone");
  const heading = useId();
  const share = useSyncExternalStore(never, canShare, () => false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(problemUrl());
      notify({ tone: "ok", title: t("copied") });
    } catch {
      notify({ tone: "er", title: t("copyFailed") });
    }
  };
  const send = async () => {
    try {
      await navigator.share({ title, url: problemUrl() });
    } catch (error) {
      // Closing the sheet is not a failure; a refused share leaves the copy.
      if (error instanceof DOMException && error.name === "AbortError") return;
      await copy();
    }
  };

  return (
    <aside
      aria-labelledby={heading}
      className="sticky bottom-14 flex flex-col gap-3 border-t border-bd bg-sf px-4 pt-3.5 pb-4"
    >
      <div className="flex gap-2.5">
        <Monitor size={18} aria-hidden="true" className="mt-px flex-none text-ac" />
        <div className="flex flex-col gap-0.5">
          <h2 id={heading} className="font-semibold">
            {t("title")}
          </h2>
          <p className="text-caption text-mu">{t("description")}</p>
        </div>
      </div>
      {share ? (
        <div className="flex gap-2">
          <Button variant="primary" className="flex-1" onClick={() => void send()}>
            <Share2 aria-hidden="true" />
            {t("share")}
          </Button>
          <Button size="icon" aria-label={t("copy")} onClick={() => void copy()}>
            <Copy aria-hidden="true" />
          </Button>
        </div>
      ) : (
        <Button variant="primary" onClick={() => void copy()}>
          <Copy aria-hidden="true" />
          {t("copy")}
        </Button>
      )}
    </aside>
  );
}
