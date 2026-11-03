import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { isLegalDocument, legalText } from "@/features/legal/documents";
import { LegalPage } from "@/features/legal/legal-page";
import { serverApi } from "@/lib/api/server";

export async function generateMetadata({
  params,
}: PageProps<"/legal/[document]">): Promise<Metadata> {
  const { document } = await params;
  if (!isLegalDocument(document)) return {};
  const t = await getTranslations("legal.documents");
  return { title: t(`${document}.title`) };
}

export default async function LegalDocumentPage({ params }: PageProps<"/legal/[document]">) {
  const { document } = await params;
  if (!isLegalDocument(document)) notFound();
  // The operator and the editions (config/legal.yaml, docs/legal.md).
  const config = await serverApi.GET("/api/v1/config");
  if (config.data === undefined) {
    throw new Error(`GET /config: ${config.error?.code ?? "no response"}`);
  }
  const { legal } = config.data;
  return (
    <LegalPage
      document={document}
      markdown={await legalText(document, legal.operator)}
      version={document === "cookies" ? null : legal.versions[document]}
      draft={legal.draft}
    />
  );
}
