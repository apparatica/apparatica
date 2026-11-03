import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { LegalIndex } from "@/features/legal/legal-page";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal");
  return { title: t("title") };
}

export default function Legal() {
  return <LegalIndex />;
}
