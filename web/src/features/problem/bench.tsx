"use client";

// The problem page (FR-PRB-01, mock-up Bench): the statement on the left, the editor and the results
// on the right, in panels whose sizes the browser remembers. The page owns the check
// (useSubmission) and the code (Workspace); Run and Submit start from the buttons or the shortcuts.
// A start the API refuses until a captcha is solved opens the captcha and starts again with it.
import { skipToken, useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState, useSyncExternalStore } from "react";
import {
  Group,
  type Layout,
  type LayoutChangedMeta,
  Panel,
  Separator,
} from "react-resizable-panels";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notify } from "@/components/ui/toast";
import { useSubmissionHistory } from "@/features/guest/submissions";
import { isFinished } from "@/features/submission/machine";
import { useSubmission } from "@/features/submission/use-submission";
import { browserApi } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { CaptchaDialog } from "./captcha-dialog";
import { clearEditorStatus } from "./editor-status";
import { EditorPane, type VersionUpdate } from "./editor-pane";
import { type BenchLayout, saveBenchLayout } from "./layout";
import { captchaRequest, checksSpentUntil } from "./limits";
import { useOpenSubmission } from "./open-submission";
import { type LeftTab, parseLeftTab, setPageQuery } from "./page-query";
import { editorDiagnostics } from "./pipeline-view";
import { ResultsPanel } from "./results-panel";
import { useCheckShortcuts } from "./shortcuts";
import { SubmissionsTab } from "./submissions-tab";
import { Workspace } from "./workspace";

export type BenchProblem = Pick<
  Schemas["ProblemDetail"],
  | "slug"
  | "version"
  | "difficulty"
  | "template"
  | "top"
  | "language"
  | "interface"
  | "changelog"
  | "pipeline"
  | "tests"
>;

export interface BenchProps {
  problem: BenchProblem;
  /** The sizes of the panels from the cookie; the defaults without it. */
  layout: Partial<BenchLayout>;
  /** From the address: the open tab of the left panel (`?tab=`)… */
  tab?: LeftTab | undefined;
  /** …and the submission to show instead of the last one (`?submission=`). */
  submission?: string | null | undefined;
  /** The statement panel, rendered by the server. */
  children: ReactNode;
}

function ResizeHandle({ label, vertical = false }: { label: string; vertical?: boolean }) {
  return (
    <Separator
      aria-label={label}
      className={cn(
        "flex-none bg-bg outline-none! data-[separator=active]:bg-ac data-[separator=focus]:bg-ac data-[separator=hover]:bg-ac",
        vertical ? "h-px" : "w-px",
      )}
    />
  );
}

/** The template of the version a draft was written for: the notice is needed if it changed. */
async function fetchTemplate(slug: string, version: number): Promise<string | null> {
  const { data } = await browserApi.GET("/api/v1/problems/{slug}/versions/{version}", {
    params: { path: { slug, version } },
  });
  return data?.template ?? null;
}

export function Bench({
  problem,
  layout,
  tab = "statement",
  submission: wanted,
  children,
}: BenchProps) {
  const t = useTranslations("problem");
  const [workspace] = useState(
    () =>
      new Workspace({
        problem: problem.slug,
        version: problem.version,
        template: problem.template,
      }),
  );
  const { draftVersion } = useSyncExternalStore(
    workspace.subscribe,
    workspace.getSnapshot,
    workspace.getSnapshot,
  );
  const submission = useSubmission({
    problem: problem.slug,
    version: problem.version,
    difficulty: problem.difficulty,
    wanted,
  });
  const history = useSubmissionHistory(problem.slug);
  const [leftTab, setLeftTab] = useState(tab);
  const opener = useOpenSubmission({ problem, workspace, submission });

  useEffect(
    () => () => {
      workspace.detach();
      clearEditorStatus();
    },
    [workspace],
  );

  // A draft of an older version: its template, unless the draft was written for the current one.
  const previous = useQuery({
    queryKey: ["problems", problem.slug, "versions", draftVersion, "template"],
    queryFn: draftVersion === null ? skipToken : () => fetchTemplate(problem.slug, draftVersion),
    staleTime: Infinity,
  });
  const update: VersionUpdate | null =
    draftVersion !== null && previous.isSuccess && previous.data !== problem.template
      ? { version: problem.version, draft: draftVersion, changelog: problem.changelog }
      : null;

  const { check, starting, error, failedAt } = submission;
  const busy = starting ?? (check !== null && !isFinished(check) ? check.kind : null);
  // The kind of the last start: the captcha starts it again.
  const [kind, setKind] = useState<"run" | "submit">("run");
  const start = (next: "run" | "submit", captcha: string | null = null) => {
    if (busy !== null) return;
    workspace.flush();
    setKind(next);
    submission.start({ kind: next, code: workspace.code(), captcha });
    setPageQuery({ submission: null });
  };
  useCheckShortcuts(start);

  // The captcha is asked once per refused start; a cancelled one stays closed.
  const captcha = captchaRequest(error, failedAt);
  const [dismissed, setDismissed] = useState<number | null>(null);

  useEffect(() => {
    if (error === null) return;
    // These have their own places: the limit panel of the results, the captcha dialog.
    if (checksSpentUntil(error, 0) !== null || captchaRequest(error, 0) !== null) return;
    notify({
      tone: "er",
      title: t("results.startFailed"),
      description: "detail" in error ? error.detail : error.message,
    });
  }, [error, t]);

  // Only what the user did is remembered, not the sizes a narrow window forces.
  const remember = (group: keyof BenchLayout) => (sizes: Layout, meta: LayoutChangedMeta) => {
    if (!meta.isUserInteraction) return;
    saveBenchLayout(group, meta.requestedLayout ?? sizes);
  };

  return (
    <Group
      id="bench"
      orientation="horizontal"
      defaultLayout={layout.columns}
      onLayoutChanged={remember("columns")}
      className="h-full min-h-0"
    >
      <Panel id="statement" defaultSize="38%" minSize="20%" maxSize="70%">
        <Tabs
          value={leftTab}
          onValueChange={(value) => {
            const next = parseLeftTab(value);
            setLeftTab(next);
            setPageQuery({ tab: next === "statement" ? null : next });
          }}
          className="flex h-full min-h-0 flex-col bg-sf"
        >
          <TabsList variant="panel" aria-label={t("tabs.label")} className="flex-none">
            <TabsTrigger value="statement">{t("tabs.statement")}</TabsTrigger>
            <TabsTrigger value="submissions">
              {t("tabs.submissions")}
              {history !== null && (
                <span className="font-mono text-[11px] text-mu">{history.length}</span>
              )}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="statement" className="min-h-0 flex-1 overflow-y-auto">
            {children}
          </TabsContent>
          <TabsContent value="submissions" className="min-h-0 flex-1 overflow-y-auto">
            <SubmissionsTab
              problem={problem}
              submissions={history}
              selected={check?.id ?? null}
              onOpen={(id) => void opener.open(id)}
            />
          </TabsContent>
        </Tabs>
        {opener.dialog}
        <CaptchaDialog
          request={captcha !== null && captcha.since !== dismissed ? captcha : null}
          onSolve={(solution) => start(kind, solution)}
          onCancel={() => setDismissed(captcha?.since ?? null)}
        />
      </Panel>
      <ResizeHandle label={t("panels.columns")} />
      <Panel id="work" minSize="30%">
        <Group
          id="bench-work"
          orientation="vertical"
          defaultLayout={layout.rows}
          onLayoutChanged={remember("rows")}
          className="h-full min-h-0"
        >
          <Panel id="editor" defaultSize="50%" minSize="15%">
            <EditorPane
              workspace={workspace}
              problem={problem}
              update={update}
              busy={busy}
              markers={editorDiagnostics(check, problem.language)}
              onCheck={start}
            />
          </Panel>
          <ResizeHandle label={t("panels.rows")} vertical />
          <Panel id="results" minSize="15%">
            <ResultsPanel
              submission={submission}
              problem={problem}
              busy={busy !== null}
              onCheck={start}
              onReveal={(line, column) => workspace.reveal(line, column)}
            />
          </Panel>
        </Group>
      </Panel>
    </Group>
  );
}
