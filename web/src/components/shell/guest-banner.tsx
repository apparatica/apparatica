"use client";

import { Users, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { closeGuestBanner } from "@/lib/guest-banner";

/** The strip over the header (sheet Guest): what a guest keeps and where. «Войти» comes with
 * accounts (Ф2); after closing only the «Гость» chip of the header remains. */
export function GuestBanner() {
  const t = useTranslations("shell.guest");
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <aside
      aria-label={t("banner")}
      className="flex flex-none items-center gap-3 border-b border-in bg-ins px-4 py-2"
    >
      <Users size={16} aria-hidden="true" className="flex-none text-in" />
      <p className="min-w-0 flex-1">{t("bannerText")}</p>
      <button
        type="button"
        aria-label={t("closeBanner")}
        onClick={() => {
          closeGuestBanner();
          setOpen(false);
        }}
        className="flex size-6 flex-none cursor-pointer items-center justify-center rounded-md text-mu hover:bg-sf2 hover:text-tx pointer-coarse:size-11"
      >
        <X size={16} aria-hidden="true" />
      </button>
    </aside>
  );
}
