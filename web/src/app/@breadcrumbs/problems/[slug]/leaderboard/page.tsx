import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { loadProblem } from "@/features/problem/load";

export default async function ProblemLeaderboardBreadcrumbs({
  params,
}: PageProps<"/problems/[slug]/leaderboard">) {
  const [t, data] = await Promise.all([
    getTranslations("shell.nav"),
    loadProblem((await params).slug),
  ]);
  if (data === null) return null;
  const { slug, title } = data.problem;
  return (
    <Breadcrumbs
      items={[
        { label: t("problems"), href: "/problems" },
        { label: title, href: `/problems/${encodeURIComponent(slug)}` },
        { label: t("problemLeaderboard") },
      ]}
    />
  );
}
