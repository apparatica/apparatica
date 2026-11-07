"use client";

// The problem page as the window allows: the Bench with the editor, or on phones (FR-MOB-02/03,
// mock-up MobTask) the tabs to read — the statement with the block «Эталон», the solutions of
// others, the leaderboard and the own submissions — with the offer to solve on a computer. Phones
// load neither the editor nor the check.
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSubmissionHistory } from "@/features/guest/submissions";
import { LeaderboardTab } from "@/features/leaderboard/leaderboard-tab";
import { SolutionsTab } from "@/features/leaderboard/solutions-tab";
import { PhoneReference } from "@/features/reference/phone-reference";
import type { BenchReference } from "@/features/reference/reference-tab";
import { submissionKeys, syncSubmissions } from "@/features/submission/api";
import { usePhone } from "@/lib/viewport";

import { Bench, type BenchProps } from "./bench";
import { DesktopOffer } from "./desktop-offer";
import { useLeftTab } from "./left-tab";
import type { LeftTab } from "./page-query";
import { SubmissionsTab } from "./submissions-tab";

/** The tab of the address a phone can show: the reference is a block of the statement there. */
function phoneTab(tab: LeftTab, problem: BenchProps["problem"]): LeftTab {
  if (tab === "reference") return "statement";
  if (tab === "leaderboard" && problem.leaderboard === null) return "statement";
  return tab;
}

function PhoneProblem({
  problem,
  tab,
  reference,
  children,
}: {
  problem: BenchProps["problem"];
  tab: LeftTab;
  reference: BenchReference | null;
  children: ReactNode;
}) {
  const t = useTranslations("problem");
  const [current, select] = useLeftTab(phoneTab(tab, problem));
  const history = useSubmissionHistory(problem.slug);
  // No check of this page reads the list of the server: the open tab does, once.
  useQuery({
    queryKey: submissionKeys.list(problem.slug),
    queryFn: () => syncSubmissions(problem.slug),
    enabled: current === "submissions",
  });
  return (
    <div className="flex min-h-full flex-col">
      <Tabs value={current} onValueChange={select} className="flex flex-1 flex-col">
        <TabsList aria-label={t("tabs.label")} className="overflow-x-auto px-4">
          <TabsTrigger value="statement" className="min-h-11 text-[13px]">
            {t("tabs.statement")}
          </TabsTrigger>
          <TabsTrigger value="solutions" className="min-h-11 text-[13px]">
            {t("tabs.solutions")}
          </TabsTrigger>
          {problem.leaderboard !== null && (
            <TabsTrigger value="leaderboard" className="min-h-11 text-[13px]">
              {t("tabs.leaderboard")}
            </TabsTrigger>
          )}
          <TabsTrigger value="submissions" className="min-h-11 text-[13px] whitespace-nowrap">
            {t("tabs.submissionsShort")}
            {history !== null && history.length > 0 && (
              <span className="font-mono text-[11px] text-mu">{history.length}</span>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="statement" className="flex-1">
          {children}
          {reference !== null && <PhoneReference problem={problem} reference={reference} />}
        </TabsContent>
        <TabsContent value="solutions" className="flex-1">
          <SolutionsTab problem={problem} />
        </TabsContent>
        {problem.leaderboard !== null && (
          <TabsContent value="leaderboard" className="flex-1">
            <LeaderboardTab problem={problem.slug} />
          </TabsContent>
        )}
        <TabsContent value="submissions" className="flex-1">
          <SubmissionsTab problem={problem} submissions={history} selected={null} />
        </TabsContent>
      </Tabs>
      <DesktopOffer title={problem.title} />
    </div>
  );
}

export function ProblemView({
  problem,
  layout,
  tab = "statement",
  submission,
  account,
  reference,
  children,
}: BenchProps) {
  const phone = usePhone();
  if (phone) {
    return (
      <PhoneProblem problem={problem} tab={tab} reference={reference ?? null}>
        {children}
      </PhoneProblem>
    );
  }
  return (
    // The window without the header (40 px) and the status bar (24 px): the panels fill it and
    // scroll inside.
    <div className="h-[calc(100dvh-4rem)]">
      <Bench
        problem={problem}
        layout={layout}
        tab={tab}
        submission={submission}
        account={account}
        reference={reference}
      >
        {children}
      </Bench>
    </div>
  );
}
