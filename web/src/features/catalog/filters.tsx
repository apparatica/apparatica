"use client";

// The controls of the catalogue (FR-CAT-02): search, level, tag and status filters, the sort, and
// the filters that are on as chips with a reset. Every change goes to the address. Phones (mock-up
// MobCatalog) toggle the levels with buttons in a row that scrolls sideways.
import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useEffect, useRef, useState } from "react";

import { TagChip } from "@/components/domain/tag-chip";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SearchInput } from "@/components/ui/input";
import type { Schemas } from "@/lib/api/client";

import { type CatalogQuery, type Sort, SORTS, STATUSES, withoutFilters } from "./query";

export const SEARCH_DELAY_MS = 300;

type Change = (query: CatalogQuery) => void;

/** The search box: the address follows the text after a pause in typing. */
function SearchBox({ query, onChange }: { query: CatalogQuery; onChange: Change }) {
  const t = useTranslations("problems.search");
  const [text, setText] = useState(query.q);
  // The text this box last sent; another `q` came from elsewhere (back, reset) and replaces it.
  const [sent, setSent] = useState(query.q);
  if (query.q !== sent) {
    setSent(query.q);
    setText(query.q);
  }
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const type = (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setText(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setSent(value);
      onChange({ ...query, q: value, page: 1 });
    }, SEARCH_DELAY_MS);
  };
  return (
    <SearchInput
      aria-label={t("label")}
      placeholder={t("placeholder")}
      value={text}
      onChange={type}
      maxLength={100}
      className="w-full sm:w-[280px]"
    />
  );
}

interface Option {
  value: string;
  label: string;
}

/** A filter of several values: the menu stays open while they are picked. */
function FilterMenu({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: Option[];
  selected: string[];
  onSelect: (values: string[]) => void;
}) {
  const t = useTranslations("problems.filters");
  const toggle = (value: string, on: boolean) =>
    onSelect(
      on
        ? options.map((option) => option.value).filter((v) => v === value || selected.includes(v))
        : selected.filter((v) => v !== value),
    );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={selected.length > 0 ? "selected" : "default"}>
          {selected.length > 0 ? t("count", { filter: label, count: selected.length }) : label}
          <ChevronDown className="size-3.5!" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 overflow-y-auto">
        {options.map((option) => (
          <DropdownMenuCheckboxItem
            key={option.value}
            checked={selected.includes(option.value)}
            onCheckedChange={(on) => toggle(option.value, on)}
            onSelect={(event) => event.preventDefault()}
          >
            {option.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SortMenu({
  sort,
  compact = false,
  onSort,
}: {
  sort: Sort;
  /** The order alone, on a plain button (phones). */
  compact?: boolean;
  onSort: (sort: Sort) => void;
}) {
  const t = useTranslations("problems.sort");
  const label = t("label", { sort: t(sort) });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={compact ? "ghost" : "default"} aria-label={compact ? label : undefined}>
          {compact ? t(sort) : label}
          <ChevronDown className="size-3.5!" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("title")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={sort}
          onValueChange={(value) => onSort(SORTS.find((item) => item === value) ?? "number")}
        >
          {SORTS.map((item) => (
            <DropdownMenuRadioItem key={item} value={item}>
              {t(item)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Phones: a button per level, «Все» for none; several levels can be on. */
function LevelToggles({
  levels,
  selected,
  all,
  onSelect,
}: {
  levels: Schemas["Difficulty"][];
  selected: string[];
  all: number;
  onSelect: (values: string[]) => void;
}) {
  const t = useTranslations("problems.filters");
  const toggle = (key: string) =>
    onSelect(
      levels.map((level) => level.key).filter((item) => (item === key) !== selected.includes(item)),
    );
  return (
    <>
      <Button
        variant={selected.length === 0 ? "selected" : "default"}
        aria-pressed={selected.length === 0}
        onClick={() => onSelect([])}
      >
        {t("all")} <span className="font-mono">{all}</span>
      </Button>
      {levels.map((level) => {
        const on = selected.includes(level.key);
        return (
          <Button
            key={level.key}
            variant={on ? "selected" : "default"}
            aria-pressed={on}
            onClick={() => toggle(level.key)}
          >
            {level.title}
          </Button>
        );
      })}
    </>
  );
}

export function CatalogFilters({
  query,
  levels,
  tags,
  total,
  all,
  phone = false,
  onChange,
}: {
  query: CatalogQuery;
  levels: Schemas["Difficulty"][];
  tags: Schemas["Tag"][];
  /** Problems that match; null while unknown. */
  total: number | null;
  /** Problems of the catalogue, whatever the filters. */
  all: number;
  phone?: boolean;
  onChange: Change;
}) {
  const t = useTranslations("problems");
  const change = (next: Partial<CatalogQuery>) => onChange({ ...query, ...next, page: 1 });
  const titleOf = (slug: string) => tags.find((tag) => tag.slug === slug)?.title ?? slug;
  const levelOf = (key: string) => levels.find((level) => level.key === key)?.title ?? key;
  const chips: { key: string; label: string; reset: Partial<CatalogQuery> }[] = [
    // Phones show the levels that are on in their buttons.
    ...(phone ? [] : query.difficulty).map((key) => ({
      key: `difficulty-${key}`,
      label: levelOf(key),
      reset: { difficulty: query.difficulty.filter((item) => item !== key) },
    })),
    ...query.tag.map((slug) => ({
      key: `tag-${slug}`,
      label: titleOf(slug),
      reset: { tag: query.tag.filter((item) => item !== slug) },
    })),
    ...query.status.map((status) => ({
      key: `status-${status}`,
      label: t("status.chip", { status }),
      reset: { status: query.status.filter((item) => item !== status) },
    })),
  ];

  const tagMenu = (
    <FilterMenu
      label={t("filters.tags")}
      options={tags.map((tag) => ({ value: tag.slug, label: tag.title }))}
      selected={query.tag}
      onSelect={(tag) => change({ tag })}
    />
  );
  const statusMenu = (
    <FilterMenu
      label={t("filters.status")}
      options={STATUSES.map((status) => ({ value: status, label: t(`status.${status}`) }))}
      selected={query.status}
      onSelect={(status) => change({ status: STATUSES.filter((item) => status.includes(item)) })}
    />
  );
  const count = total !== null && (
    <span className="text-[12.5px] text-mu" aria-live="polite">
      {t.rich("total", {
        count: total,
        n: (chunks) => <span className="font-mono text-tx">{chunks}</span>,
      })}
    </span>
  );

  return (
    <div className="flex flex-col gap-2">
      {phone ? (
        <>
          <SearchBox query={query} onChange={onChange} />
          <div
            role="group"
            aria-label={t("filters.label")}
            className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]"
          >
            <LevelToggles
              levels={levels}
              selected={query.difficulty}
              all={all}
              onSelect={(difficulty) => change({ difficulty })}
            />
            {tagMenu}
            {statusMenu}
          </div>
          <div className="flex items-center justify-between gap-2">
            {count}
            <SortMenu sort={query.sort} compact onSort={(sort) => change({ sort })} />
          </div>
        </>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <SearchBox query={query} onChange={onChange} />
          <FilterMenu
            label={t("filters.difficulty")}
            options={levels.map((level) => ({ value: level.key, label: level.title }))}
            selected={query.difficulty}
            onSelect={(difficulty) => change({ difficulty })}
          />
          {tagMenu}
          {statusMenu}
          <div className="flex-1" />
          {count}
          <SortMenu sort={query.sort} onSort={(sort) => change({ sort })} />
        </div>
      )}
      {chips.length > 0 && (
        <ul
          aria-label={t("filters.active")}
          className="flex flex-wrap items-center gap-1.5 pointer-coarse:gap-x-3 pointer-coarse:gap-y-6"
        >
          {chips.map((chip) => (
            <li key={chip.key}>
              <TagChip removable asChild>
                <button
                  type="button"
                  className="touch-target cursor-pointer"
                  onClick={() => change(chip.reset)}
                >
                  {chip.label}
                </button>
              </TagChip>
            </li>
          ))}
          <li>
            <Button
              variant="ghost"
              className="h-6 px-1.5"
              onClick={() => onChange(withoutFilters(query))}
            >
              {t("filters.reset")}
            </Button>
          </li>
        </ul>
      )}
    </div>
  );
}
