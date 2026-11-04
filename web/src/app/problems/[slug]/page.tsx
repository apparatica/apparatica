import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { LAYOUT_COOKIE, parseBenchLayout } from "@/features/problem/layout";
import { loadProblem, loadServerDraft } from "@/features/problem/load";
import { parseLeftTab } from "@/features/problem/page-query";
import { ProblemStatement } from "@/features/problem/problem-statement";
import { ProblemView } from "@/features/problem/problem-view";
import { SESSION_COOKIE } from "@/lib/session";
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
  const [data, account] = await Promise.all([
    loadProblem(slug),
    loadServerDraft(slug, jar.get(SESSION_COOKIE)?.value ?? null),
  ]);
  if (data === null) notFound();
  const layout = parseBenchLayout(jar.get(LAYOUT_COOKIE)?.value);
  const { tab, submission } = await searchParams;
  return (
    // Another problem gets a new workspace: its draft, its editor.
    <ProblemView
      key={data.problem.slug}
      problem={data.problem}
      layout={layout}
      tab={parseLeftTab(tab)}
      submission={typeof submission === "string" && UUID.test(submission) ? submission : null}
      account={account}
    >
      <ProblemStatement {...data} />
    </ProblemView>
  );
}
