"use client";

// The editor panel of a problem page (mock-up Bench): the file tab, the reset to the template,
// Run and Submit with their shortcuts (FR-EDT-03/04), the notice about a new version of the problem
// (FR-PRB-05) and Monaco, loaded lazily with a skeleton in its place (NFR-PERF-06).
import { Check, Play, RotateCcw, Send, TriangleAlert } from "lucide-react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useRef, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Shortcut, useApple } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { editorLanguage, solutionFile } from "@/features/editor/languages";
import { ariaKeys, formatKeys } from "@/lib/shortcuts";

import { EditorSkeleton } from "./skeletons";
import { RUN_KEYS, SUBMIT_KEYS, UNDO_KEYS } from "./shortcuts";
import type { Workspace } from "./workspace";

const CodeEditor = dynamic(() => import("@/features/editor/code-editor"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

export interface VersionUpdate {
  version: number;
  /** The version of the draft. */
  draft: number;
  changelog: string | null;
}

export interface EditorPaneProps {
  workspace: Workspace;
  problem: { slug: string; top: string; language: string };
  /** The draft was written for an older version with another template (FR-PRB-05). */
  update: VersionUpdate | null;
  /** The kind being started or checked: its button shows progress, the other one waits. */
  busy: "run" | "submit" | null;
  onCheck: (kind: "run" | "submit") => void;
}

export function EditorPane({ workspace, problem, update, busy, onCheck }: EditorPaneProps) {
  const t = useTranslations("problem");
  const apple = useApple();
  const [confirming, setConfirming] = useState(false);
  // Confirmed: the reset runs when the dialog has closed, so the focus goes to the editor (for
  // Ctrl+Z) and not back to the button that opened the dialog.
  const confirmed = useRef(false);
  const { ready, savedAt } = useSyncExternalStore(
    workspace.subscribe,
    workspace.getSnapshot,
    workspace.getSnapshot,
  );
  const file = solutionFile(problem.top, problem.language);

  return (
    <div className="flex h-full min-h-0 flex-col bg-sf">
      <div className="flex h-9 flex-none items-stretch border-b border-bd bg-sf2">
        <div className="flex items-center gap-2 border-r border-bd bg-sf px-3.5 shadow-[inset_0_2px_0_var(--ac)]">
          <span className="font-mono text-[12.5px]">{file}</span>
          {savedAt !== null && (
            <Check size={14} className="text-ok" role="img" aria-label={t("editor.saved")} />
          )}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1.5 pr-2">
          <Tooltip content={t("editor.reset")}>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("editor.reset")}
              disabled={!ready}
              onClick={() => setConfirming(true)}
            >
              <RotateCcw aria-hidden="true" />
            </Button>
          </Tooltip>
          <Tooltip content={t("editor.runHint")}>
            <Button
              variant="outline"
              loading={busy === "run"}
              disabled={busy === "submit"}
              aria-keyshortcuts={ariaKeys(RUN_KEYS, apple)}
              onClick={() => onCheck("run")}
            >
              {busy !== "run" && <Play aria-hidden="true" />}
              {t("editor.run")}
              <Shortcut keys={RUN_KEYS} aria-hidden="true" />
            </Button>
          </Tooltip>
          <Tooltip content={t("editor.submitHint")}>
            <Button
              variant="primary"
              loading={busy === "submit"}
              disabled={busy === "run"}
              aria-keyshortcuts={ariaKeys(SUBMIT_KEYS, apple)}
              onClick={() => onCheck("submit")}
            >
              {busy !== "submit" && <Send aria-hidden="true" />}
              {t("editor.submit")}
              <Shortcut keys={SUBMIT_KEYS} aria-hidden="true" />
            </Button>
          </Tooltip>
        </div>
      </div>
      {update !== null && (
        <VersionNotice
          update={update}
          ready={ready}
          onReset={() => setConfirming(true)}
          onDismiss={() => workspace.acknowledge()}
        />
      )}
      <div className="min-h-0 flex-1 bg-ed">
        <CodeEditor
          defaultValue={workspace.initialCode()}
          language={editorLanguage(problem.language).monaco}
          path={`${problem.slug}/${file}`}
          label={t("editor.label", { file })}
          loading={<EditorSkeleton />}
          onMount={(editor) => workspace.attach(editor)}
        />
      </div>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent
          className="max-w-[420px]"
          onCloseAutoFocus={(event) => {
            if (!confirmed.current) return;
            confirmed.current = false;
            event.preventDefault();
            workspace.reset();
          }}
        >
          <DialogHeader className="pb-4">
            <DialogTitle>{t("resetDialog.title")}</DialogTitle>
            <DialogDescription>
              {t("resetDialog.description", { undo: formatKeys(UNDO_KEYS, apple) })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={() => setConfirming(false)}>{t("resetDialog.cancel")}</Button>
            <Button
              variant="primary"
              onClick={() => {
                confirmed.current = true;
                setConfirming(false);
              }}
            >
              {t("resetDialog.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function VersionNotice({
  update,
  ready,
  onReset,
  onDismiss,
}: {
  update: VersionUpdate;
  ready: boolean;
  onReset: () => void;
  onDismiss: () => void;
}) {
  const t = useTranslations("problem.updated");
  return (
    <div
      role="status"
      className="flex flex-none items-start gap-2.5 border-b border-bd bg-wns px-3.5 py-2"
    >
      <TriangleAlert size={16} className="mt-0.5 flex-none text-wn" aria-hidden="true" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="font-medium text-wn">{t("title", { version: update.version })}</span>
        <span>{t("description", { draft: update.draft })}</span>
        {update.changelog !== null && (
          <span className="text-mu">
            {t("changes")}: {update.changelog}
          </span>
        )}
      </div>
      <div className="flex flex-none gap-1.5">
        <Button disabled={!ready} onClick={onReset}>
          {t("reset")}
        </Button>
        <Button variant="ghost" onClick={onDismiss}>
          {t("dismiss")}
        </Button>
      </div>
    </div>
  );
}
