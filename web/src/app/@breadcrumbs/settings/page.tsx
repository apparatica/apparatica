import { useTranslations } from "next-intl";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";

export default function SettingsBreadcrumbs() {
  const t = useTranslations("settings");
  return <Breadcrumbs items={[{ label: t("title") }]} />;
}
