// The OG picture of a problem (FR-SHR-02): its level, title, tags, acceptance and the formula of
// its leaderboard. Rendered on the first request and kept for `revalidate` seconds.
import { notFound } from "next/navigation";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { loadProblem } from "@/features/problem/load";
import { problemCard } from "@/features/share/card";
import { OG_SIZE, renderOg } from "@/features/share/og-image";

export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 600;

/** No paths at build time: each is rendered on its first request and then cached (ISR). */
export function generateStaticParams() {
  return [];
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const data = await loadProblem((await params).slug);
  if (data === null) notFound();
  const { problem, levels, tags } = data;
  return renderOg(problemCard(problem, findDifficulty(levels, problem.difficulty) ?? null, tags));
}
