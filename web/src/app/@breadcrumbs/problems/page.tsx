import { useTranslations } from "next-intl";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";

export default function CatalogBreadcrumbs() {
  const t = useTranslations("shell.nav");
  return <Breadcrumbs items={[{ label: t("problems") }]} />;
}
