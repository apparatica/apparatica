import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { Bench } from "@/features/problem/bench";
import { LAYOUT_COOKIE, parseBenchLayout } from "@/features/problem/layout";
import { loadProblem } from "@/features/problem/load";
import { ProblemStatement } from "@/features/problem/problem-statement";
import { statementSummary } from "@/lib/statement/summary";

export async function generateMetadata({
  params,
}: PageProps<"/problems/[slug]">): Promise<Metadata> {
  const data = await loadProblem((await params).slug);
  if (data === null) return {};
  const { title, statement_md } = data.problem;
  const description = statementSummary(statement_md);
  return { title, description, openGraph: { title, description, type: "article" } };
}

export default async function ProblemPage({ params }: PageProps<"/problems/[slug]">) {
  const data = await loadProblem((await params).slug);
  if (data === null) notFound();
  const layout = parseBenchLayout((await cookies()).get(LAYOUT_COOKIE)?.value);
  return (
    // The window without the header (40 px) and the status bar (24 px), or the bottom bar (56 px)
    // on phones: the panels fill the window and scroll inside.
    <div className="h-[calc(100dvh-6rem)] sm:h-[calc(100dvh-4rem)]">
      {/* Another problem gets a new workspace: its draft, its editor. */}
      <Bench key={data.problem.slug} problem={data.problem} layout={layout}>
        <ProblemStatement {...data} />
      </Bench>
    </div>
  );
}
