// The legal documents (FR-AUTH-06, specs/08 §1, no mock-up): the list of them and a document — its
// title, the edition a first login accepts, a draft notice until a lawyer has read the texts, the
// text. Rendered by the server, like a statement.
import { ChevronRight, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Statement } from "@/lib/statement/statement";

import { LEGAL_DOCUMENTS, type LegalDocument } from "./documents";

function Page({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-4 px-4 pt-3 pb-8 sm:px-8 sm:pt-6">
      {children}
    </div>
  );
}

export function LegalIndex() {
  const t = useTranslations("legal");
  return (
    <Page>
      <div className="flex flex-col gap-0.5">
        <h1 className="text-title-1">{t("title")}</h1>
        <p className="text-mu">{t("subtitle")}</p>
      </div>
      <ul className="flex flex-col overflow-hidden rounded-md border border-bd bg-sf">
        {LEGAL_DOCUMENTS.map((document) => (
          <li key={document} className="border-bd not-last:border-b">
            <Link
              href={`/legal/${document}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-sf2"
            >
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="font-medium">{t(`documents.${document}.title`)}</span>
                <span className="text-caption text-mu">
                  {t(`documents.${document}.description`)}
                </span>
              </span>
              <ChevronRight size={16} className="shrink-0 text-mu" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export interface LegalPageProps {
  document: LegalDocument;
  /** The text, the operator filled in. */
  markdown: string;
  /** The edition a first login accepts, `YYYY-MM-DD`; null for a list for reference. */
  version: string | null;
  draft: boolean;
}

export function LegalPage({ document, markdown, version, draft }: LegalPageProps) {
  const t = useTranslations("legal");
  const format = useFormatter();
  // An edition is a calendar date, not a moment: the same day in any time zone.
  const edition = (date: string) =>
    format.dateTime(new Date(date), { dateStyle: "long", timeZone: "UTC" });
  return (
    <Page>
      <article className="flex flex-col gap-4">
        <header className="flex flex-col gap-0.5">
          <h1 className="text-title-1">{t(`documents.${document}.title`)}</h1>
          {version !== null && (
            <p className="text-caption text-mu">{t("edition", { date: edition(version) })}</p>
          )}
        </header>
        {draft && (
          <p
            role="note"
            className="flex items-start gap-2 rounded-md bg-wns px-3 py-2 text-[12.5px] leading-[18px] text-wn"
          >
            <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
            {t("draft")}
          </p>
        )}
        {/* Cells break between words: the columns of a narrow table keep their words whole. */}
        <Statement markdown={markdown} className="[&_td]:wrap-break-word [&_th]:wrap-break-word" />
      </article>
    </Page>
  );
}
