// The path in the header (specs/08 §2, mock-ups Catalog and Bench): "Задачи / Синхронный FIFO".
// Pages fill it through the `breadcrumbs` slot of the layout.
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Fragment, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

export interface Crumb {
  label: string;
  /** The last crumb, the page itself, has no link. */
  href?: string;
}

function Trail({ children }: { children: ReactNode }) {
  const t = useTranslations("shell");
  return (
    <>
      <span aria-hidden="true" className="hidden h-[18px] w-px flex-none bg-bd sm:block" />
      <nav
        aria-label={t("breadcrumbs")}
        className="hidden min-w-0 items-center gap-2 text-[12.5px] text-mu sm:flex"
      >
        {children}
      </nav>
    </>
  );
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <Trail>
      {items.map((item, index) => (
        <Fragment key={index}>
          {index > 0 && <span aria-hidden="true">/</span>}
          {item.href === undefined ? (
            <span aria-current="page" className="truncate text-tx">
              {item.label}
            </span>
          ) : (
            <Link href={item.href} className="rounded-md whitespace-nowrap hover:text-tx">
              {item.label}
            </Link>
          )}
        </Fragment>
      ))}
    </Trail>
  );
}

export function BreadcrumbsSkeleton() {
  return (
    <Trail>
      <Skeleton className="h-2.5 w-[130px]" />
    </Trail>
  );
}
