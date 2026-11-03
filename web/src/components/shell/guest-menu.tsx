"use client";

import { FileText, Monitor, Moon, Sun, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { loginHref } from "@/lib/session";
import { parseTheme, THEMES } from "@/lib/theme";

import { useTheme } from "./theme";

export const THEME_ICONS = { system: Monitor, light: Sun, dark: Moon } as const;

/** The choice of the theme in a menu of the header (specs/08 §2). */
export function ThemeItems() {
  const t = useTranslations("shell.theme");
  const { theme, setTheme } = useTheme();
  return (
    <>
      <DropdownMenuLabel>{t("title")}</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(parseTheme(value))}>
        {THEMES.map((item) => {
          const Icon = THEME_ICONS[item];
          return (
            <DropdownMenuRadioItem key={item} value={item}>
              <Icon aria-hidden="true" />
              {t(item)}
            </DropdownMenuRadioItem>
          );
        })}
      </DropdownMenuRadioGroup>
    </>
  );
}

/** The legal documents (FR-AUTH-06): the shell has no footer, so the menus link to them. */
export function DocumentsItem() {
  const t = useTranslations("shell");
  return (
    <DropdownMenuItem asChild>
      <Link href="/legal">
        <FileText aria-hidden="true" />
        {t("documents")}
      </Link>
    </DropdownMenuItem>
  );
}

/** The "Guest" chip of the header (sheet Guest) with its menu, the theme, and «Войти» beside it,
 * returning to this page; the login pages do not show the button. */
export function GuestMenu() {
  const t = useTranslations("shell");
  const path = usePathname();
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="inline-flex h-[22px] cursor-pointer items-center gap-1.5 rounded-sm border border-bc px-2 font-mono text-[11px] text-mu hover:bg-sf2 hover:text-tx data-[state=open]:bg-sf2 pointer-coarse:h-11">
          <User size={12} aria-hidden="true" />
          {t("guest.label")}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <ThemeItems />
          <DropdownMenuSeparator />
          <DocumentsItem />
        </DropdownMenuContent>
      </DropdownMenu>
      {!path.startsWith("/login") && (
        <Button asChild className="h-[26px]">
          <Link href={loginHref(path)}>{t("guest.login")}</Link>
        </Button>
      )}
    </>
  );
}
