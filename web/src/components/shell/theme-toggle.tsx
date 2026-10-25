"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { applyTheme, nextTheme, type Theme } from "@/lib/theme";

const ICONS = { system: Monitor, light: Sun, dark: Moon } as const;

/** Cycles system → light → dark. Moves into the user menu and the command palette (T1.9). */
export function ThemeToggle({ initial }: { initial: Theme }) {
  const t = useTranslations("shell.theme");
  const [theme, setTheme] = useState(initial);
  const Icon = ICONS[theme];
  const label = t("label", { theme: t(theme) });
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => {
        const next = nextTheme(theme);
        applyTheme(next);
        setTheme(next);
      }}
      className="flex size-[30px] items-center justify-center rounded-md text-mu hover:bg-sf2 hover:text-tx"
    >
      <Icon size={16} aria-hidden="true" />
    </button>
  );
}
