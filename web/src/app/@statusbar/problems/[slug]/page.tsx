import { getTranslations } from "next-intl/server";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { loadProblem } from "@/features/problem/load";
import { ProblemStatusBar } from "@/features/problem/status-bar";

export default async function ProblemStatus({ params }: PageProps<"/problems/[slug]">) {
  const [t, data] = await Promise.all([
    getTranslations("problem"),
    loadProblem((await params).slug),
  ]);
  if (data === null) return null;
  const { problem, levels } = data;
  // A language without a title in the messages is shown by its key.
  const language = `language.${problem.language}` as "language.systemverilog";
  return (
    <ProblemStatusBar
      level={findDifficulty(levels, problem.difficulty)?.difficulty.title ?? problem.difficulty}
      language={t.has(language) ? t(language) : problem.language}
    />
  );
}
