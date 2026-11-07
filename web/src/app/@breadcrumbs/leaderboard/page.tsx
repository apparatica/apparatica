import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";

export default async function GlobalLeaderboardBreadcrumbs() {
  const t = await getTranslations("shell.nav");
  return <Breadcrumbs items={[{ label: t("leaderboard") }]} />;
}
