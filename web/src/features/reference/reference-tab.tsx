"use client";

// The tab «Эталон» of the problem page (FR-REF-01, sheet LeftTabsB): the reference solutions,
// rendered by the server (`ReferenceView`), or — until the visitor's own accepted Submit — a lock
// with the reason and «Перейти к редактору». The page reads them as the visitor sees them and
// reads them again when a Submit is accepted (`Bench`).
import { Lock, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useRef, useTransition } from "react";

import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api/client";

/** The reference of the problem page, read by the server. */
export type BenchReference =
  | {
      state: "open";
      /** The tab, rendered by the server. */
      view: ReactNode;
      /** For «Сравнить с эталоном». */
      solutions: Schemas["ReferenceSolution"][];
    }
  | { state: "locked" }
  | { state: "failed" };

function Locked({ onEdit }: { onEdit?: (() => void) | undefined }) {
  const t = useTranslations("reference.locked");
  return (
    <div className="flex flex-col items-center gap-2.5 px-10 py-10 text-center">
      <div
        aria-hidden="true"
        className="mb-3 flex w-full max-w-[270px] flex-col gap-2 rounded-md border border-bd bg-ed p-4 blur-[1.5px]"
      >
        {[70, 92, 58, 84, 46, 76].map((width, index) => (
          <span key={index} className="h-2 rounded-sm bg-sf2" style={{ width: `${width}%` }} />
        ))}
      </div>
      <Lock size={22} aria-hidden="true" className="text-mu" />
      <h2 className="text-[14px] font-medium">{t("title")}</h2>
      <p className="max-w-[340px] text-mu">{t("body")}</p>
      <p className="max-w-[340px] text-caption text-mu">{t("why")}</p>
      {onEdit !== undefined && (
        <Button variant="primary" onClick={onEdit} className="mt-1">
          {t("edit")}
        </Button>
      )}
    </div>
  );
}

function Failed() {
  const t = useTranslations("reference");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <div className="flex flex-col items-center gap-2.5 px-10 py-12 text-center">
      <p className="text-mu">{t("failed")}</p>
      <Button loading={pending} onClick={() => startTransition(() => router.refresh())}>
        <RefreshCw aria-hidden="true" />
        {t("retry")}
      </Button>
    </div>
  );
}

export function ReferenceTab({
  reference,
  onEdit,
}: {
  reference: BenchReference;
  onEdit?: (() => void) | undefined;
}) {
  if (reference.state === "locked") return <Locked onEdit={onEdit} />;
  if (reference.state === "failed") return <Failed />;
  return reference.view;
}

/** Reads the page again once for an accepted Submit: it opens a reference that was locked. */
export function RefreshOnAccepted({ check }: { check: string }) {
  const router = useRouter();
  const done = useRef<string | null>(null);
  useEffect(() => {
    if (done.current === check) return;
    done.current = check;
    router.refresh();
  }, [check, router]);
  return null;
}
