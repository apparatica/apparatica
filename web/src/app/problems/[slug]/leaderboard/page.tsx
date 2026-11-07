import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { LeaderboardPage } from "@/features/leaderboard/leaderboard-page";
import { loadBoard } from "@/features/leaderboard/load";
import { parseBoardQuery } from "@/features/leaderboard/query";
import { loadProblem } from "@/features/problem/load";
import { SESSION_COOKIE } from "@/lib/session";

export async function generateMetadata({
  params,
}: PageProps<"/problems/[slug]/leaderboard">): Promise<Metadata> {
  const data = await loadProblem((await params).slug);
  if (data === null || data.problem.leaderboard === null) return {};
  const t = await getTranslations("leaderboard.page");
  const title = t("metaTitle", { title: data.problem.title });
  const description = t("description", { title: data.problem.title });
  return { title, description, openGraph: { title, description, type: "website" } };
}

export default async function ProblemLeaderboardPage({
  params,
  searchParams,
}: PageProps<"/problems/[slug]/leaderboard">) {
  const { slug } = await params;
  const data = await loadProblem(slug);
  if (data === null || data.problem.leaderboard === null) notFound();
  const session = (await cookies()).get(SESSION_COOKIE)?.value ?? null;
  const loaded = await loadBoard(slug, parseBoardQuery(await searchParams), session);
  if (loaded === null) notFound();
  const { problem, levels } = data;
  return (
    <LeaderboardPage
      problem={problem}
      level={findDifficulty(levels, problem.difficulty) ?? null}
      board={loaded.board}
      query={loaded.query}
    />
  );
}
