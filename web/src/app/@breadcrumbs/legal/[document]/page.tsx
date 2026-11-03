import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { isLegalDocument } from "@/features/legal/documents";

export default async function LegalDocumentBreadcrumbs({ params }: PageProps<"/legal/[document]">) {
  const [t, { document }] = await Promise.all([getTranslations("legal"), params]);
  if (!isLegalDocument(document)) return null;
  return (
    <Breadcrumbs
      items={[{ label: t("title"), href: "/legal" }, { label: t(`documents.${document}.title`) }]}
    />
  );
}
