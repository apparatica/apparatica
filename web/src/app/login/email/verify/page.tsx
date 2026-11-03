import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { VerifyLogin } from "@/features/account/verify-login";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("login.verify");
  return { title: t("pageTitle"), robots: { index: false } };
}

export default function VerifyLoginPage() {
  return <VerifyLogin />;
}
