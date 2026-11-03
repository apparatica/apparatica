import { useTranslations } from "next-intl";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";

export default function LoginBreadcrumbs() {
  const t = useTranslations("login");
  return <Breadcrumbs items={[{ label: t("pageTitle") }]} />;
}
