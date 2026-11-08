import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { loadProblem } from "@/features/problem/load";
import { authorNames } from "@/features/profile/author";
import { loadSolution } from "@/features/solution/load";
import { SolutionPage } from "@/features/solution/solution-page";
import { visitorOf } from "@/lib/api/server";

async function load(id: string) {
  const { session, guest } = visitorOf(await cookies());
  const solution = await loadSolution(id, session, guest);
  if (solution === null) return null;
  const data = await loadProblem(solution.problem.slug);
  return data === null ? null : { solution, ...data };
}

export async function generateMetadata({
  params,
}: PageProps<"/solutions/[id]">): Promise<Metadata> {
  const data = await load((await params).id);
  if (data === null) return {};
  const t = await getTranslations("solution");
  const { solution } = data;
  const nick = authorNames(await getTranslations("author")).of(solution.author);
  const title = t("metaTitle", { nick, title: solution.problem.title });
  // Metrics, author and place are public; the code is not (FR-SOL-02).
  const description =
    solution.placement === null
      ? t("description", { nick, title: solution.problem.title })
      : t("descriptionPlace", {
          nick,
          title: solution.problem.title,
          rank: solution.placement.rank,
          total: solution.placement.total,
        });
  return { title, description, openGraph: { title, description, type: "article" } };
}

export default async function PublicSolutionPage({ params }: PageProps<"/solutions/[id]">) {
  const data = await load((await params).id);
  if (data === null) notFound();
  const { solution, problem, levels } = data;
  return (
    <SolutionPage
      solution={solution}
      problem={problem}
      level={findDifficulty(levels, problem.difficulty) ?? null}
    />
  );
}
