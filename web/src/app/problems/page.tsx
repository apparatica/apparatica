import type { Metadata } from "next";
import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";

import { Catalog } from "@/features/catalog/catalog";
import { loadCatalog } from "@/features/catalog/load";
import { parseCatalogQuery } from "@/features/catalog/query";
import { SESSION_COOKIE } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("problems");
  return { title: t("title") };
}

export default async function ProblemsPage({ searchParams }: PageProps<"/problems">) {
  const query = parseCatalogQuery(await searchParams);
  const session = (await cookies()).get(SESSION_COOKIE)?.value ?? null;
  const data = await loadCatalog(query, session);
  return <Catalog query={query} data={data} />;
}
