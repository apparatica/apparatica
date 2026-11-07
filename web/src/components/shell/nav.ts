import { ChartColumn, List, type LucideIcon, User } from "lucide-react";

import { profileHref } from "@/features/profile/href";

export type NavKey = "problems" | "leaderboard" | "profile";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
}

// Sections of the left rail and of the bottom bar on phones (specs/08 §2). The dashboard (Ф4)
// joins with its page.
export const NAV: readonly NavItem[] = [
  { key: "problems", href: "/problems", icon: List },
  { key: "leaderboard", href: "/leaderboard", icon: ChartColumn },
];

/** The own profile of a signed-in user: at the bottom of the rail, the last of the bottom bar. */
export const profileItem = (nick: string): NavItem => ({
  key: "profile",
  href: profileHref(nick),
  icon: User,
});

export function isActive(item: NavItem, pathname: string): boolean {
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
