import Link from "next/link";
import { useTranslations } from "next-intl";

// The full error pages (PageErrors) come with the components of Ф1.
export default function NotFound() {
  const t = useTranslations("errors.notFound");
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col items-start gap-2 px-4 pt-6 sm:px-8">
      <h1 className="text-title-1">{t("title")}</h1>
      <p className="text-mu">{t("description")}</p>
      <Link href="/problems" className="text-ac underline underline-offset-2">
        {t("toProblems")}
      </Link>
    </div>
  );
}
