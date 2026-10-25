import { List, type LucideIcon } from "lucide-react";

export type NavKey = "problems";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
}

// Sections of the left rail and of the bottom bar on phones (specs/08 §2). Rating (Ф3), dashboard
// (Ф4) and profile (Ф2) join with their pages.
export const NAV: readonly NavItem[] = [{ key: "problems", href: "/problems", icon: List }];

export function isActive(item: NavItem, pathname: string): boolean {
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
