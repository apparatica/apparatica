"use client";

// The captcha before a check (FR-GST-05, sheet ModalsB) or a login link: after `428
// CAPTCHA_REQUIRED` the guest solves an ALTCHA challenge and the request goes again with it. When
// checks were only too frequent, the wait is shown too: once it is over, the check goes without the
// captcha. The hint that signed-in users see fewer captchas is T2.6a.
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiUrl } from "@/lib/api/browser";
import { formatCountdown, useCountdown } from "@/lib/clock";

import { AltchaWidget } from "./altcha-widget";
import type { CaptchaRequest } from "./request";

const timer = (chunks: ReactNode) => <span className="font-mono text-tx">{chunks}</span>;

export interface CaptchaDialogProps {
  /** Open while set. */
  request: CaptchaRequest | null;
  /** Start the check again: with the solution, or without one after the wait. */
  onSolve: (solution: string | null) => void;
  onCancel: () => void;
  /** What waits for the captcha: a check of a solution or a login link. */
  purpose?: "check" | "login" | undefined;
}

export function CaptchaDialog({ request, onSolve, onCancel, purpose }: CaptchaDialogProps) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onCancel()}>
      {request !== null && (
        <DialogContent className="max-w-[560px]">
          {/* A new request asks for a new challenge. */}
          <CaptchaForm
            key={request.since}
            request={request}
            onSolve={onSolve}
            onCancel={onCancel}
            purpose={purpose}
          />
        </DialogContent>
      )}
    </Dialog>
  );
}

function CaptchaForm({
  request,
  onSolve,
  onCancel,
  purpose = "check",
}: CaptchaDialogProps & { request: CaptchaRequest }) {
  const t = useTranslations("captcha");
  const [solution, setSolution] = useState<string | null>(null);
  const left = useCountdown(request.until, request.since);
  const waited = request.until !== null && left === null;
  let wait: ReactNode = null;
  if (left !== null) wait = t.rich("wait", { time: formatCountdown(left), timer });
  else if (waited) wait = t("waited");
  return (
    <>
      <DialogHeader className="pb-4">
        <DialogTitle>{t("title")}</DialogTitle>
        <DialogDescription>
          {t(purpose === "login" && request.reason === "always" ? "alwaysLogin" : request.reason)}{" "}
          {wait}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="pt-0">
        <AltchaWidget challengeUrl={apiUrl(request.challengeUrl)} onChange={setSolution} />
      </DialogBody>
      <DialogFooter>
        <Button onClick={onCancel}>{t("cancel")}</Button>
        <Button
          variant="primary"
          disabled={solution === null && !waited}
          onClick={() => onSolve(solution)}
        >
          {t("submit")}
        </Button>
      </DialogFooter>
    </>
  );
}
