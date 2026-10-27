"use client";

import { CircleCheck, CircleX, Info, type LucideIcon, TriangleAlert, X } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { toast, Toaster as Sonner } from "sonner";

import { cn } from "@/lib/utils";

// Notifications of sheet CmpD: a 3 px bar on the left in the colour of the tone, its icon, a title
// and a caption, a close button. Sonner places and times them; the card is ours.
export type Tone = "ok" | "wn" | "er" | "in";

const TONES: Record<Tone, { icon: LucideIcon; bar: string; text: string }> = {
  ok: { icon: CircleCheck, bar: "border-l-ok", text: "text-ok" },
  wn: { icon: TriangleAlert, bar: "border-l-wn", text: "text-wn" },
  er: { icon: CircleX, bar: "border-l-er", text: "text-er" },
  in: { icon: Info, bar: "border-l-in", text: "text-in" },
};

export interface ToastProps {
  tone: Tone;
  title: ReactNode;
  description?: ReactNode;
}

export function ToastCard({
  tone,
  title,
  description,
  onClose,
}: ToastProps & { onClose: () => void }) {
  const t = useTranslations("ui");
  const { icon: Icon, bar, text } = TONES[tone];
  return (
    <div
      className={cn(
        "flex w-[356px] max-w-[calc(100vw-32px)] items-start gap-2.5 rounded-md border border-l-[3px] border-bd bg-sf px-3 py-2.5 text-tx shadow-pop",
        bar,
      )}
    >
      <Icon size={16} aria-hidden="true" className={cn("mt-0.5 flex-none", text)} />
      <div className="flex min-w-0 flex-1 flex-col leading-[1.4]">
        <span className="font-medium">{title}</span>
        {description != null && <span className="text-caption text-mu">{description}</span>}
      </div>
      <button
        type="button"
        aria-label={t("close")}
        onClick={onClose}
        className="flex size-5 flex-none cursor-pointer items-center justify-center rounded-sm text-tx hover:bg-sf2"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

/** Shows a notification; returns its id for `dismiss`. */
export function notify(props: ToastProps & { duration?: number }): string | number {
  const { duration, ...card } = props;
  return toast.custom((id) => <ToastCard {...card} onClose={() => toast.dismiss(id)} />, {
    ...(duration !== undefined && { duration }),
  });
}

export const dismiss = toast.dismiss;

/** The place of notifications: bottom right, once in the layout. */
export function Toaster() {
  return <Sonner position="bottom-right" offset={16} mobileOffset={16} />;
}
