import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("problems");
  return { title: t("title") };
}

// The catalogue comes in T1.12; the page holds the place in the shell.
export default function ProblemsPage() {
  const t = useTranslations("problems");
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-1 px-4 pt-6 sm:px-8">
      <h1 className="text-title-1">{t("title")}</h1>
      <p className="text-mu">{t("placeholder")}</p>
    </div>
  );
}
