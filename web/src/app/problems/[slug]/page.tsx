import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { LAYOUT_COOKIE, parseBenchLayout } from "@/features/problem/layout";
import { loadProblem, loadReference, loadServerDraft } from "@/features/problem/load";
import { parseLeftTab } from "@/features/problem/page-query";
import { ProblemStatement } from "@/features/problem/problem-statement";
import { ProblemView } from "@/features/problem/problem-view";
import type { BenchReference } from "@/features/reference/reference-tab";
import { ReferenceView } from "@/features/reference/reference-view";
import { problemCard } from "@/features/share/card";
import { ProblemCardProvider } from "@/features/share/problem-card";
import { visitorOf } from "@/lib/api/server";
import { statementSummary } from "@/lib/statement/summary";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({
  params,
}: PageProps<"/problems/[slug]">): Promise<Metadata> {
  const data = await loadProblem((await params).slug);
  if (data === null) return {};
  const { title, statement_md } = data.problem;
  const description = statementSummary(statement_md);
  return { title, description, openGraph: { title, description, type: "article" } };
}

export default async function ProblemPage({ params, searchParams }: PageProps<"/problems/[slug]">) {
  const { slug } = await params;
  const jar = await cookies();
  const visitor = visitorOf(jar);
  const [data, account] = await Promise.all([
    loadProblem(slug),
    loadServerDraft(slug, visitor.session),
  ]);
  if (data === null) notFound();
  // The reference solutions as this visitor sees them (FR-REF-01), rendered here like the statement.
  const loaded = data.problem.reference === null ? null : await loadReference(slug, visitor);
  let reference: BenchReference | null = null;
  if (loaded?.state === "open") {
    reference = {
      state: "open",
      view: <ReferenceView page={loaded.page} problem={data.problem} />,
      solutions: loaded.page.solutions,
    };
  } else if (loaded !== null) {
    reference = { state: loaded.state };
  }
  const layout = parseBenchLayout(jar.get(LAYOUT_COOKIE)?.value);
  const { tab, submission } = await searchParams;
  const card = problemCard(
    data.problem,
    findDifficulty(data.levels, data.problem.difficulty) ?? null,
    data.tags,
  );
  return (
    // Another problem gets a new workspace: its draft, its editor.
    <ProblemCardProvider key={data.problem.slug} card={card}>
      <ProblemView
        problem={data.problem}
        layout={layout}
        tab={parseLeftTab(tab)}
        submission={typeof submission === "string" && UUID.test(submission) ? submission : null}
        account={account}
        reference={reference}
      >
        <ProblemStatement {...data} />
      </ProblemView>
    </ProblemCardProvider>
  );
}
