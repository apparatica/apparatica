// The path in the header (specs/08 §2, mock-ups Catalog and Bench): "Задачи / Синхронный FIFO".
// Pages fill it through the `breadcrumbs` slot of the layout. Phones show the page alone, as a
// title, after a back link to the crumb before it (mock-ups MobCatalog and MobTask); the header
// hides the brand next to the title and the logo next to the back link.
import { ChevronLeft } from "lucide-react";
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

/** The header of a phone: the back link and the title of the page. */
function PhoneTitle({ items }: { items: Crumb[] }) {
  const t = useTranslations("shell");
  const page = items.at(-1);
  const parent = items.at(-2);
  if (page === undefined) return null;
  return (
    <div data-phone-title className="-ml-1.5 flex min-w-0 items-center sm:hidden">
      {parent?.href !== undefined && (
        <Link
          data-phone-back
          href={parent.href}
          aria-label={t("back", { page: parent.label })}
          className="flex size-11 flex-none items-center justify-center rounded-md text-tx"
        >
          <ChevronLeft size={22} aria-hidden="true" />
        </Link>
      )}
      <span className="truncate text-[15px] font-semibold">{page.label}</span>
    </div>
  );
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <>
      <PhoneTitle items={items} />
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
    </>
  );
}

export function BreadcrumbsSkeleton() {
  return (
    <>
      <Skeleton data-phone-title className="h-3 w-[130px] sm:hidden" />
      <Trail>
        <Skeleton className="h-2.5 w-[130px]" />
      </Trail>
    </>
  );
}
