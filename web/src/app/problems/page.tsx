import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Catalog } from "@/features/catalog/catalog";
import { loadCatalog } from "@/features/catalog/load";
import { parseCatalogQuery } from "@/features/catalog/query";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("problems");
  return { title: t("title") };
}

export default async function ProblemsPage({ searchParams }: PageProps<"/problems">) {
  const query = parseCatalogQuery(await searchParams);
  const data = await loadCatalog(query);
  return <Catalog query={query} data={data} />;
}
