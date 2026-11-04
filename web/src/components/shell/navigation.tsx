"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { useAccount } from "@/features/account/session";
import { cn } from "@/lib/utils";

import { isActive, NAV, type NavItem, profileItem } from "./nav";

/** The sections and, for a signed-in user, their profile. */
function useSections(): { sections: readonly NavItem[]; profile: NavItem | null } {
  const me = useAccount();
  return { sections: NAV, profile: me == null ? null : profileItem(me.nick) };
}

function RailLink({ item, className }: { item: NavItem; className?: string }) {
  const t = useTranslations("shell");
  const active = isActive(item, usePathname());
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-label={t(`nav.${item.key}`)}
      title={t(`nav.${item.key}`)}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex size-9 items-center justify-center rounded-md",
        active ? "bg-acs text-ac" : "text-mu hover:bg-sf2 hover:text-tx",
        className,
      )}
    >
      <Icon size={18} aria-hidden="true" />
    </Link>
  );
}

/** Left rail of sections, 48 px; hidden below 640 px, where the bottom bar takes over. The profile
 * is at the bottom (mock-up Profile). */
export function Rail() {
  const t = useTranslations("shell");
  const { sections, profile } = useSections();
  return (
    <nav
      aria-label={t("sections")}
      className="hidden w-12 flex-none flex-col items-center gap-1 bg-sf py-2 sm:flex"
    >
      {sections.map((item) => (
        <RailLink key={item.key} item={item} />
      ))}
      {profile !== null && <RailLink item={profile} className="mt-auto" />}
    </nav>
  );
}

/** Bottom bar of sections below 640 px; targets are 44 px high (HANDOFF.md, mobile). */
export function BottomNav() {
  const t = useTranslations("shell");
  const pathname = usePathname();
  const { sections, profile } = useSections();
  return (
    <nav
      aria-label={t("sections")}
      className="fixed inset-x-0 bottom-0 flex h-14 border-t border-bd bg-sf sm:hidden"
    >
      {[...sections, ...(profile === null ? [] : [profile])].map((item) => {
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
