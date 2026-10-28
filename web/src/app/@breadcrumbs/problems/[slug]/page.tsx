import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { loadProblem } from "@/features/problem/load";

export default async function ProblemBreadcrumbs({ params }: PageProps<"/problems/[slug]">) {
  const [t, data] = await Promise.all([
    getTranslations("shell.nav"),
    loadProblem((await params).slug),
  ]);
  if (data === null) return null;
  return (
    <Breadcrumbs
      items={[{ label: t("problems"), href: "/problems" }, { label: data.problem.title }]}
    />
  );
}
