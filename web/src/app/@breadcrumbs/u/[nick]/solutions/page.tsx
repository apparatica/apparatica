import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { profileHref } from "@/features/profile/href";

// «nick / Решения»: the nick leads back to the profile.
export default async function UserSolutionsBreadcrumbs({
  params,
}: PageProps<"/u/[nick]/solutions">) {
  const { nick } = await params;
  const t = await getTranslations("profile.solutions");
  return <Breadcrumbs items={[{ label: nick, href: profileHref(nick) }, { label: t("title") }]} />;
}
