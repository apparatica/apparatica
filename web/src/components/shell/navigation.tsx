"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import { isActive, NAV } from "./nav";

/** Left rail of sections, 48 px; hidden below 640 px, where the bottom bar takes over. */
export function Rail() {
  const t = useTranslations("shell");
  const pathname = usePathname();
  return (
    <nav
      aria-label={t("sections")}
      className="hidden w-12 flex-none flex-col items-center gap-1 bg-sf py-2 sm:flex"
    >
      {NAV.map((item) => {
        const active = isActive(item, pathname);
        const Icon = item.icon;
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-label={t(`nav.${item.key}`)}
            title={t(`nav.${item.key}`)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex size-9 items-center justify-center rounded-md",
              active ? "bg-acs text-ac" : "text-mu hover:bg-sf2 hover:text-tx",
            )}
          >
            <Icon size={18} aria-hidden="true" />
          </Link>
        );
      })}
    </nav>
  );
}

/** Bottom bar of sections below 640 px; targets are 44 px high (HANDOFF.md, mobile). */
export function BottomNav() {
  const t = useTranslations("shell");
  const pathname = usePathname();
  return (
    <nav
      aria-label={t("sections")}
      className="fixed inset-x-0 bottom-0 flex h-14 border-t border-bd bg-sf sm:hidden"
    >
      {NAV.map((item) => {
        const active = isActive(item, pathname);
        const Icon = item.icon;
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 text-caption",
              active ? "text-ac" : "text-mu",
            )}
          >
            <Icon size={18} aria-hidden="true" />
            <span>{t(`nav.${item.key}`)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
