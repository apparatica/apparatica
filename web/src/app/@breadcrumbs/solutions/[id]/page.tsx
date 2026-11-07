import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { leaderboardPath } from "@/features/leaderboard/query";
import { loadSolution } from "@/features/solution/load";
import { visitorOf } from "@/lib/api/server";

// «Задачи / ‹задача› / Рейтинг / Решение ‹ник›» (mock-up Solution); without a leaderboard of the
// problem there is no «Рейтинг».
export default async function SolutionBreadcrumbs({ params }: PageProps<"/solutions/[id]">) {
  const { session, guest } = visitorOf(await cookies());
  const [t, solution] = await Promise.all([
    getTranslations("shell.nav"),
    loadSolution((await params).id, session, guest),
  ]);
  if (solution === null) return null;
  const { slug, title } = solution.problem;
  return (
    <Breadcrumbs
      items={[
        { label: t("problems"), href: "/problems" },
        { label: title, href: `/problems/${encodeURIComponent(slug)}` },
        ...(solution.order.length > 0
          ? [{ label: t("problemLeaderboard"), href: leaderboardPath(slug) }]
          : []),
        { label: t("solution", { nick: solution.author.nick }) },
      ]}
    />
  );
}
