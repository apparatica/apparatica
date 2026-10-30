"use client";

// The problem page as the window allows: the Bench with the editor, or on phones (FR-MOB-02,
// mock-up MobTask) the statement and «Мои отправки» to read, with the offer to solve on a computer.
// Phones load neither the editor nor the check.
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSubmissionHistory } from "@/features/guest/submissions";
import { submissionKeys, syncSubmissions } from "@/features/submission/api";
import { usePhone } from "@/lib/viewport";

import { Bench, type BenchProps } from "./bench";
import { DesktopOffer } from "./desktop-offer";
import { useLeftTab } from "./left-tab";
import type { LeftTab } from "./page-query";
import { SubmissionsTab } from "./submissions-tab";

function PhoneProblem({
  problem,
  tab,
  children,
}: {
  problem: BenchProps["problem"];
  tab: LeftTab;
  children: ReactNode;
}) {
  const t = useTranslations("problem");
  const [current, select] = useLeftTab(tab);
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
        <TabsList aria-label={t("tabs.label")} className="px-4">
          <TabsTrigger value="statement" className="min-h-11 text-[13px]">
            {t("tabs.statement")}
          </TabsTrigger>
          <TabsTrigger value="submissions" className="min-h-11 text-[13px]">
            {t("tabs.submissions")}
            {history !== null && history.length > 0 && (
              <span className="font-mono text-[11px] text-mu">{history.length}</span>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="statement" className="flex-1">
          {children}
        </TabsContent>
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
  children,
}: BenchProps) {
  const phone = usePhone();
  if (phone) {
    return (
      <PhoneProblem problem={problem} tab={tab}>
        {children}
      </PhoneProblem>
    );
  }
  return (
    // The window without the header (40 px) and the status bar (24 px): the panels fill it and
    // scroll inside.
    <div className="h-[calc(100dvh-4rem)]">
      <Bench problem={problem} layout={layout} tab={tab} submission={submission}>
        {children}
      </Bench>
    </div>
  );
}
