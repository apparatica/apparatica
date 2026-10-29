"use client";

import { Monitor, Moon, Sun, User } from "lucide-react";
import { useTranslations } from "next-intl";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { parseTheme, THEMES } from "@/lib/theme";

import { useTheme } from "./theme";

export const THEME_ICONS = { system: Monitor, light: Sun, dark: Moon } as const;

/** The "Guest" chip of the header (sheet Guest) and its menu: the theme until accounts (Ф2). */
export function GuestMenu() {
  const t = useTranslations("shell");
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="inline-flex h-[22px] cursor-pointer items-center gap-1.5 rounded-sm border border-bc px-2 font-mono text-[11px] text-mu hover:bg-sf2 hover:text-tx data-[state=open]:bg-sf2 pointer-coarse:h-11">
        <User size={12} aria-hidden="true" />
        {t("guest.label")}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("theme.title")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(value) => setTheme(parseTheme(value))}
        >
          {THEMES.map((item) => {
            const Icon = THEME_ICONS[item];
            return (
              <DropdownMenuRadioItem key={item} value={item}>
                <Icon aria-hidden="true" />
                {t(`theme.${item}`)}
              </DropdownMenuRadioItem>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
