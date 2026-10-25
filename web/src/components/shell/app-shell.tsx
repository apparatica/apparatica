import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { Theme } from "@/lib/theme";

import { BottomNav, Rail } from "./navigation";
import { ThemeToggle } from "./theme-toggle";

function Logo() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
      className="stroke-ac"
    >
      <rect x="4" y="3" width="17" height="18" rx="2" />
      <path d="M4 9.5l5 2.5-5 2.5" />
    </svg>
  );
}

/** Header, left rail (bottom bar below 640 px) and the page; the layout of the mock-ups. */
export function AppShell({ theme, children }: { theme: Theme; children: ReactNode }) {
  const t = useTranslations("shell");
  return (
    <div className="flex min-h-dvh flex-col bg-bg text-tx">
      <header className="flex h-10 flex-none items-center gap-4 border-b border-bd bg-sf px-3">
        <Link href="/" className="flex items-center gap-2 rounded-md font-semibold">
          <Logo />
          <span>{t("brand")}</span>
        </Link>
        <div className="flex-1" />
        <ThemeToggle initial={theme} />
      </header>
      <div className="flex min-h-0 flex-1 gap-px">
        <Rail />
        <main className="min-w-0 flex-1 bg-sf pb-14 sm:pb-0">{children}</main>
      </div>
      <BottomNav />
    </div>
  );
}
