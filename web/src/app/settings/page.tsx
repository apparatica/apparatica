import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SettingsPage } from "@/features/account/settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings");
  return { title: t("title"), robots: { index: false } };
}

export default function Settings() {
  return <SettingsPage />;
}
