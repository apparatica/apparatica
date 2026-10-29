"use client";

// The command palette (specs/08 §2): Ctrl+K (⌘K) or "Quick search" in the header; problems found
// by GET /problems?q= with their difficulty, and actions of the site. Sheet CmpD.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CodeXml, List, type LucideIcon, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useDeferredValue, useEffect, useState } from "react";

import { DifficultyBadge, findDifficulty } from "@/components/domain/difficulty-badge";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandLoading,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Shortcut, useApple } from "@/components/ui/kbd";
import { browserApi } from "@/lib/api/browser";
import { useConfig } from "@/lib/config";
import { ariaKeys, isShortcut, type Key } from "@/lib/shortcuts";
import { THEMES } from "@/lib/theme";

import { THEME_ICONS } from "./guest-menu";
import { useTheme } from "./theme";

export const PALETTE_KEYS: readonly Key[] = ["Mod", "K"];
const FOUND = 8;

async function findProblems(q: string) {
  const { data, error } = await browserApi.GET("/api/v1/problems", {
    params: { query: { q, per_page: FOUND } },
  });
  if (error !== undefined) throw error;
  return data.items;
}

interface Action {
  id: string;
  label: string;
  icon: LucideIcon;
  run: () => void;
}

export function CommandPalette() {
  const t = useTranslations("shell.palette");
  const router = useRouter();
  const apple = useApple();
  const { setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const q = useDeferredValue(query.trim());
  const levels = useConfig().data?.difficulties ?? [];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isShortcut(event, PALETTE_KEYS, apple)) {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [apple]);

  const found = useQuery({
    queryKey: ["problems", "search", q],
    queryFn: () => findProblems(q),
    enabled: open && q !== "",
    placeholderData: keepPreviousData,
  });

  const close = () => {
    setOpen(false);
    setQuery("");
  };
  const actions: Action[] = [
    {
      id: "problems",
      label: t("actions.problems"),
      icon: List,
      run: () => router.push("/problems"),
    },
    ...THEMES.map((theme) => ({
      id: `theme-${theme}`,
      label: t(`actions.${theme}`),
      icon: THEME_ICONS[theme],
      run: () => setTheme(theme),
    })),
  ];
  const shown = actions.filter((action) => action.label.toLowerCase().includes(q.toLowerCase()));
  const problems = q === "" ? [] : (found.data ?? []);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-keyshortcuts={ariaKeys(PALETTE_KEYS, apple)}
        className="flex h-[26px] cursor-pointer items-center gap-2 rounded-md border border-bc bg-ed px-2.5 text-mu hover:text-tx max-sm:size-[30px] max-sm:justify-center max-sm:px-0 sm:w-[258px] pointer-coarse:h-11 max-sm:pointer-coarse:size-11"
      >
        <Search size={14} aria-hidden="true" className="flex-none" />
        <span className="flex-1 text-left max-sm:sr-only">{t("open")}</span>
        <Shortcut keys={PALETTE_KEYS} aria-hidden="true" className="max-sm:hidden" />
      </button>
      <Dialog open={open} onOpenChange={(value) => (value ? setOpen(true) : close())}>
        <DialogContent closable={false} className="top-[15dvh] max-w-[640px] translate-y-0">
          <DialogTitle className="sr-only">{t("title")}</DialogTitle>
          <DialogDescription className="sr-only">{t("description")}</DialogDescription>
          <Command shouldFilter={false} loop>
            <CommandInput
              value={query}
              onValueChange={setQuery}
              placeholder={t("placeholder")}
              hint="Esc"
            />
            <CommandList>
              {found.isFetching && problems.length === 0 && (
                <CommandLoading>{t("loading")}</CommandLoading>
              )}
              {!found.isFetching && <CommandEmpty>{t("empty")}</CommandEmpty>}
              {problems.length > 0 && (
                <CommandGroup heading={t("problems")}>
                  {problems.map((problem) => {
                    const level = findDifficulty(levels, problem.difficulty);
                    return (
                      <CommandItem
                        key={problem.slug}
                        value={`problem:${problem.slug}`}
                        onSelect={() => {
                          close();
                          router.push(`/problems/${problem.slug}`);
                        }}
                      >
                        <CodeXml aria-hidden="true" />
                        <span className="flex-1 truncate">{problem.title}</span>
                        {level && <DifficultyBadge {...level} compact />}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              )}
              {shown.length > 0 && (
                <CommandGroup heading={t("actions.title")}>
                  {shown.map((action) => (
                    <CommandItem
                      key={action.id}
                      value={action.id}
                      onSelect={() => {
                        close();
                        action.run();
                      }}
                    >
                      <action.icon aria-hidden="true" />
                      <span className="flex-1">{action.label}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
    </>
  );
}
