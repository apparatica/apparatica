import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The pages to show: the first, the last and the neighbours of the current one, with gaps. */
export function pageItems(page: number, count: number): (number | "gap")[] {
  if (count <= 7) return Array.from({ length: count }, (_, index) => index + 1);
  const from = Math.max(2, Math.min(page - 1, count - 4));
  const to = Math.min(count - 1, Math.max(page + 1, 5));
  const items: (number | "gap")[] = [1];
  if (from > 2) items.push(from === 3 ? 2 : "gap");
  for (let item = from; item <= to; item++) items.push(item);
  if (to < count - 1) items.push(to === count - 2 ? count - 1 : "gap");
  items.push(count);
  return items;
}

// Sheet CmpD: 28 px squares, mono 12 px, the current page --acs with an --ac border.
const square =
  "inline-flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 font-mono text-caption pointer-coarse:h-11 pointer-coarse:min-w-11";
const link = cn(square, "border border-bc hover:bg-sf2");

function Step({
  href,
  label,
  children,
}: {
  href: string | null;
  label: string;
  children: ReactNode;
}) {
  return href === null ? (
    <span
      aria-disabled="true"
      aria-label={label}
      className={cn(square, "border border-bc opacity-45")}
    >
      {children}
    </span>
  ) : (
    <Link href={href} aria-label={label} className={link}>
      {children}
    </Link>
  );
}

/** Pages as links: `href(page)` is the address of a page. */
export function Pagination({
  page,
  count,
  href,
  className,
}: {
  page: number;
  count: number;
  href: (page: number) => string;
  className?: string;
}) {
  const t = useTranslations("ui.pagination");
  if (count <= 1) return null;
  return (
    <nav aria-label={t("label")} className={cn("flex items-center gap-1", className)}>
      <Step href={page > 1 ? href(page - 1) : null} label={t("previous")}>
        <ChevronLeft size={14} aria-hidden="true" />
      </Step>
      {pageItems(page, count).map((item, index) =>
        item === "gap" ? (
          <span key={`gap-${index}`} className={cn(square, "text-mu")} aria-hidden="true">
            …
          </span>
        ) : item === page ? (
          <span
            key={item}
            aria-current="page"
            className={cn(square, "border border-ac bg-acs font-semibold text-ac")}
          >
            {item}
          </span>
        ) : (
          <Link
            key={item}
            href={href(item)}
            aria-label={t("page", { page: item })}
            className={link}
          >
            {item}
          </Link>
        ),
      )}
      <Step href={page < count ? href(page + 1) : null} label={t("next")}>
        <ChevronRight size={14} aria-hidden="true" />
      </Step>
    </nav>
  );
}
