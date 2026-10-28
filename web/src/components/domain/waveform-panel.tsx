"use client";

// The container of the waveforms (components.md, sheet CmpC; FR-WAV-02): a 32 px header with the
// title on the left and "47 тактов · FST 2,4 кБ" and the tools on the right, the viewer under it.
// Five states: normal (the viewer), loading (skeleton rows), empty ("Волн пока нет"), error
// ("Не удалось загрузить волны" with "Повторить"), too big (the size and "Скачать FST"). The viewer
// stays mounted in every state, under an opaque cover: a frame that boots or holds a file keeps
// them. Not hidden by CSS: browsers stop rendering a hidden frame of another origin, and Surfer
// runs on animation frames.
import { CircleX, Download, FileX, type LucideIcon, Play, RotateCw } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type WaveformPanelState =
  | { kind: "normal" }
  | { kind: "loading"; caption?: string | undefined }
  | {
      kind: "empty";
      title?: string | undefined;
      caption?: string | undefined;
      /** E.g. "Пересоздать волны" or a download. */
      action?: ReactNode;
    }
  | {
      kind: "error";
      title?: string | undefined;
      caption?: string | undefined;
      onRetry?: (() => void) | undefined;
      retrying?: boolean | undefined;
    }
  /** `size`: "48 МБ"; `downloadHref`: the FST. */
  | { kind: "tooBig"; size: string; downloadHref?: string | undefined };

export interface WaveformPanelProps {
  state: WaveformPanelState;
  /** Left of the header; "Волны" by default. */
  title?: ReactNode;
  /** Right of the header: "47 тактов · FST 2,4 кБ". */
  info?: ReactNode;
  /** Buttons at the right end of the header, in the normal state. */
  tools?: ReactNode;
  /** The viewer: shown in the normal state, kept (covered) in the others. */
  children?: ReactNode;
  className?: string | undefined;
}

function Message({
  icon: Icon,
  tone,
  title,
  caption,
  children,
}: {
  icon: LucideIcon;
  tone: string;
  title: string;
  caption?: string | undefined;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-6 text-center">
      <Icon size={20} aria-hidden="true" className={cn("mb-1", tone)} />
      <p className="text-[13px] font-medium text-tx">{title}</p>
      {caption !== undefined && <p className="max-w-[420px] text-caption text-mu">{caption}</p>}
      {children !== undefined && <div className="mt-1.5 flex gap-2">{children}</div>}
    </div>
  );
}

export function DownloadFst({ href }: { href: string }) {
  const t = useTranslations("domain.waves");
  return (
    <Button asChild>
      <a href={href} download>
        <Download aria-hidden="true" />
        {t("download")}
      </a>
    </Button>
  );
}

function Overlay({ state }: { state: Exclude<WaveformPanelState, { kind: "normal" }> }) {
  const t = useTranslations("domain.waves");
  switch (state.kind) {
    case "loading":
      return (
        <div role="status" aria-label={state.caption ?? t("loading")} className="w-full px-2.5">
          <div className="flex flex-col gap-3.5 py-4">
            {[0, 1, 2, 3].map((row) => (
              <div key={row} className="flex items-center gap-2.5">
                <Skeleton className="h-3 w-12 flex-none" />
                <Skeleton className="h-3 flex-1" />
              </div>
            ))}
          </div>
          {state.caption !== undefined && (
            <p className="text-center text-caption text-mu">{state.caption}</p>
          )}
        </div>
      );
    case "empty":
      return (
        <Message
          icon={Play}
          tone="text-tx"
          title={state.title ?? t("empty")}
          caption={state.caption ?? t("emptyCaption")}
        >
          {state.action}
        </Message>
      );
    case "error":
      return (
        <Message
          icon={CircleX}
          tone="text-er"
          title={state.title ?? t("error")}
          caption={state.caption ?? t("errorCaption")}
        >
          {state.onRetry !== undefined && (
            <Button loading={state.retrying ?? false} onClick={state.onRetry}>
              <RotateCw aria-hidden="true" />
              {t("retry")}
            </Button>
          )}
        </Message>
      );
    case "tooBig":
      return (
        <Message
          icon={FileX}
          tone="text-wn"
          title={t("tooBig", { size: state.size })}
          caption={t("tooBigCaption")}
        >
          {state.downloadHref !== undefined && <DownloadFst href={state.downloadHref} />}
        </Message>
      );
  }
}

export function WaveformPanel({
  state,
  title,
  info,
  tools,
  children,
  className,
}: WaveformPanelProps) {
  const t = useTranslations("domain.waves");
  const normal = state.kind === "normal";
  return (
    <section
      aria-label={t("label")}
      data-state={state.kind}
      className={cn("flex h-full min-h-0 flex-col bg-ed", className)}
    >
      <div className="flex h-8 flex-none items-center justify-between gap-3 border-b border-bd bg-sf px-3">
        <h3 className="min-w-0 truncate font-mono text-label text-mu uppercase">
          {title ?? t("label")}
        </h3>
        <div className="flex flex-none items-center gap-2">
          {info !== undefined && <span className="font-mono text-label text-mu">{info}</span>}
          {normal && tools}
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        {children !== undefined && (
          <div aria-hidden={!normal} inert={!normal} className="absolute inset-0">
            {children}
          </div>
        )}
        {!normal && (
          <div className="absolute inset-0 z-10 flex items-center justify-center overflow-y-auto bg-ed">
            <Overlay state={state} />
          </div>
        )}
      </div>
    </section>
  );
}
