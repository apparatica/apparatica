"use client";

// Opening a submission from «Мои отправки» (FR-PRB-06): its code goes to the editor as one edit
// (Ctrl+Z brings the draft back), its results to the results panel, its id to the address. A draft
// that no submission holds is replaced only after a confirmation.
import { useTranslations } from "next-intl";
import { type ReactNode, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApple } from "@/components/ui/kbd";
import { notify } from "@/components/ui/toast";
import { findSubmission } from "@/features/submission/api";
import type { Submission } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import type { ApiError } from "@/lib/api/client";
import { formatKeys } from "@/lib/shortcuts";

import { setPageQuery } from "./page-query";
import { UNDO_KEYS } from "./shortcuts";
import type { Workspace } from "./workspace";

export interface OpenSubmissionOptions {
  problem: { slug: string; template: string };
  workspace: Workspace;
  submission: Pick<SubmissionState, "submission" | "show">;
}

export function useOpenSubmission({ problem, workspace, submission }: OpenSubmissionOptions): {
  open: (id: string) => Promise<void>;
  dialog: ReactNode;
} {
  const t = useTranslations("problem.submissions");
  const apple = useApple();
  const [pending, setPending] = useState<Submission | null>(null);
  // Confirmed: the code is replaced when the dialog has closed, so the focus goes to the editor.
  const confirmed = useRef<Submission | null>(null);

  const apply = (found: Submission) => {
    workspace.replace(found.code);
    submission.show(found);
    setPageQuery({ submission: found.id });
  };

  const open = async (id: string) => {
    let found: Submission | null;
    try {
      found = await findSubmission(id, problem.slug);
    } catch (error) {
      const failure = error as ApiError | Error;
      const description = "detail" in failure ? failure.detail : failure.message;
      notify({ tone: "er", title: t("openFailed"), description });
      return;
    }
    if (found === null) {
      notify({ tone: "wn", title: t("gone"), description: t("goneDescription") });
      return;
    }
    // Nothing is lost when the editor holds the code of a submission or the template.
    const code = workspace.code();
    const held = [found.code, problem.template, submission.submission?.code];
    if (held.includes(code)) apply(found);
    else setPending(found);
  };

  const dialog = (
    <Dialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
      <DialogContent
        className="max-w-[420px]"
        onCloseAutoFocus={(event) => {
          const found = confirmed.current;
          if (found === null) return;
          confirmed.current = null;
          event.preventDefault();
          apply(found);
        }}
      >
        <DialogHeader className="pb-4">
          <DialogTitle>{t("openDialog.title")}</DialogTitle>
          <DialogDescription>
            {t("openDialog.description", { undo: formatKeys(UNDO_KEYS, apple) })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => setPending(null)}>{t("openDialog.cancel")}</Button>
          <Button
            variant="primary"
            onClick={() => {
              confirmed.current = pending;
              setPending(null);
            }}
          >
            {t("openDialog.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { open, dialog };
}
