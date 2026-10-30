"use client";

// The captcha before a check (FR-GST-05, sheet ModalsB): after `428 CAPTCHA_REQUIRED` the guest
// solves an ALTCHA challenge and the check starts again with it. When checks were only too frequent,
// the wait is shown too: once it is over, the check goes without the captcha. The hint that
// signed-in users see fewer captchas comes with accounts (Ф2).
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
import { AltchaWidget } from "@/features/captcha/altcha-widget";
import { apiUrl } from "@/lib/api/browser";
import { useCountdown } from "@/lib/clock";

import { type CaptchaRequest, formatCountdown } from "./limits";

const timer = (chunks: ReactNode) => <span className="font-mono text-tx">{chunks}</span>;

export interface CaptchaDialogProps {
  /** Open while set. */
  request: CaptchaRequest | null;
  /** Start the check again: with the solution, or without one after the wait. */
  onSolve: (solution: string | null) => void;
  onCancel: () => void;
}

export function CaptchaDialog({ request, onSolve, onCancel }: CaptchaDialogProps) {
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
          {t(request.reason)} {wait}
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
