"use client";

import { Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { closeGuestBanner } from "@/lib/guest-banner";
import { loginHref } from "@/lib/session";

/** The strip over the header (sheet Guest): what a guest keeps and where, and «Войти», returning
 * to this page. After closing only the «Гость» chip of the header remains; the login pages do not
 * show the strip. */
export function GuestBanner() {
  const t = useTranslations("shell.guest");
  const path = usePathname();
  const [open, setOpen] = useState(true);
  if (!open || path.startsWith("/login")) return null;
  return (
    <aside
      aria-label={t("banner")}
      className="flex flex-none items-center gap-3 border-b border-in bg-ins px-4 py-2"
    >
      <Users size={16} aria-hidden="true" className="flex-none text-in" />
      <p className="min-w-0 flex-1">{t("bannerText")}</p>
      <Button variant="primary" asChild className="h-7 flex-none">
        <Link href={loginHref(path)}>{t("login")}</Link>
      </Button>
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
