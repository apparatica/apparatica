import { List, type LucideIcon, User } from "lucide-react";

import { profileHref } from "@/features/profile/href";

export type NavKey = "problems" | "profile";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
}

// Sections of the left rail and of the bottom bar on phones (specs/08 §2). Rating (Ф3) and
// dashboard (Ф4) join with their pages.
export const NAV: readonly NavItem[] = [{ key: "problems", href: "/problems", icon: List }];

/** The own profile of a signed-in user: at the bottom of the rail, the last of the bottom bar. */
export const profileItem = (nick: string): NavItem => ({
  key: "profile",
  href: profileHref(nick),
  icon: User,
});

export function isActive(item: NavItem, pathname: string): boolean {
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
