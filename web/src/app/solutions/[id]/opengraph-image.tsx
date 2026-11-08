// The OG picture of a public solution (FR-SHR-02, mock-up Og): the problem, the verdict, the
// metrics of the synthesis, the place and the author; never the code. Read as a visitor without
// cookies sees it, rendered on the first request and kept for `revalidate` seconds: the place
// moves as others submit.
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { loadProblem } from "@/features/problem/load";
import { authorNames } from "@/features/profile/author";
import { solutionCard } from "@/features/share/card";
import { OG_SIZE, renderOg } from "@/features/share/og-image";
import { loadSolution } from "@/features/solution/load";

export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 600;

/** No paths at build time: each is rendered on its first request and then cached (ISR). */
export function generateStaticParams() {
  return [];
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const solution = await loadSolution((await params).id, null, null);
  if (solution === null) notFound();
  const data = await loadProblem(solution.problem.slug);
  const level =
    data === null ? null : (findDifficulty(data.levels, solution.problem.difficulty) ?? null);
  return renderOg(solutionCard(solution, level, authorNames(await getTranslations("author"))));
}
