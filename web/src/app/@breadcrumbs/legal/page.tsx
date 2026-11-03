import { useTranslations } from "next-intl";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";

export default function LegalBreadcrumbs() {
  const t = useTranslations("legal");
  return <Breadcrumbs items={[{ label: t("title") }]} />;
}
