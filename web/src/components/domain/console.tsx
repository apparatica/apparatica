"use client";

import { ArrowDown, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { notify } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

// The console of the results (components.md, sheet CmpB): mono 12.5/19 px; stage separators
// `── lint ──` and info lines in --mu, success --ok, warning --wn, error --er; "file:line[:col]"
// references are links in --ac (FR-CON-02). Below: copy, follow the output and "to the bottom"
// (FR-CON-03). Following is on by default and goes off when the user scrolls up.

export type ConsoleTone = "plain" | "info" | "ok" | "warning" | "error";

export interface ConsoleLine {
  /** `separator`: the start of a stage; `notice`: a mark between dotted rules (a lost stream). */
  kind: "line" | "separator" | "notice";
  tone: ConsoleTone;
  text: string;
}

export interface SourceLink {
  file: string;
  line: number;
  column: number | null;
}

export interface ConsoleProps {
  lines: readonly ConsoleLine[];
  /** What goes on right now, under the output: elapsed time, a test that runs. Not copied. */
  live?: readonly ConsoleLine[] | undefined;
  /** Shown while there are no lines. */
  empty?: ReactNode;
  /** The files whose references lead somewhere; the others stay text. */
  isLink?: ((file: string) => boolean) | undefined;
  onLink?: ((link: SourceLink) => void) | undefined;
  className?: string | undefined;
}

const TONES: Record<ConsoleTone, string> = {
  plain: "text-tx",
  info: "text-mu",
  ok: "text-ok",
  warning: "text-wn",
  error: "text-er",
};

// `sync_fifo.sv:24:17`: a file with an extension, a line and maybe a column.
const REFERENCE = /(?<![\w./-])([\w./-]*\w\.[A-Za-z]\w*):(\d+)(?::(\d+))?/g;

/** The text of a line cut at its file references. */
export function splitReferences(text: string): (string | (SourceLink & { text: string }))[] {
  const parts: (string | (SourceLink & { text: string }))[] = [];
  let from = 0;
  for (const match of text.matchAll(REFERENCE)) {
    const [whole, file = "", line = "", column] = match;
    if (match.index > from) parts.push(text.slice(from, match.index));
    parts.push({
      text: whole,
      file,
      line: Number(line),
      column: column === undefined ? null : Number(column),
    });
    from = match.index + whole.length;
  }
  if (from < text.length) parts.push(text.slice(from));
  return parts;
}

/** A line as it is copied. */
export function lineText({ kind, text }: ConsoleLine): string {
  if (kind === "separator") return `── ${text} ──`;
  if (kind === "notice") return `┄┄ ${text} ┄┄`;
  return text;
}

// Closer to the end than this, the output is at the bottom.
const BOTTOM_SLACK_PX = 4;

function atBottom(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_SLACK_PX;
}

function Row({
  line,
  isLink,
  onLink,
}: {
  line: ConsoleLine;
  isLink: ConsoleProps["isLink"];
  onLink: ConsoleProps["onLink"];
}) {
  const tone = TONES[line.tone];
  if (line.kind === "separator") {
    return (
      <div className="flex items-center gap-2 text-mu">
        <span className="flex-none">── {line.text}</span>
        <span aria-hidden="true" className="h-px max-w-[380px] flex-1 bg-current" />
      </div>
    );
  }
  if (line.kind === "notice") {
    return <div className={tone}>┄┄ {line.text} ┄┄</div>;
  }
  return (
    <div className={tone}>
      {splitReferences(line.text).map((part, index) => {
        if (typeof part === "string") return part;
        if (isLink?.(part.file) !== true) return part.text;
        return (
          <button
            // The parts of a line never move: the index is their identity.
            key={index}
            type="button"
            className="cursor-pointer text-ac underline underline-offset-2 hover:no-underline"
            onClick={() => onLink?.({ file: part.file, line: part.line, column: part.column })}
          >
            {part.text}
          </button>
        );
      })}
    </div>
  );
}

export function Console({ lines, live = [], empty, isLink, onLink, className }: ConsoleProps) {
  const t = useTranslations("domain.console");
  const scroller = useRef<HTMLDivElement>(null);
  const lastTop = useRef(0);
  const [follow, setFollow] = useState(true);

  // Scrolls to the end and remembers where that is, so that it is not taken for the user's scroll.
  const scrollToEnd = () => {
    const element = scroller.current;
    if (element === null) return;
    element.scrollTop = element.scrollHeight;
    lastTop.current = element.scrollTop;
  };

  // Following: every new line (and the live rows) keeps the end in sight.
  useLayoutEffect(() => {
    if (follow) scrollToEnd();
  }, [lines, live, follow]);

  const toBottom = () => {
    scrollToEnd();
    setFollow(true);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.map(lineText).join("\n"));
      notify({ tone: "ok", title: t("copied") });
    } catch {
      notify({ tone: "er", title: t("copyFailed") });
    }
  };

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div
        ref={scroller}
        role="log"
        // The status of the check is announced by the panel; the lines are not read out.
        aria-live="off"
        aria-label={t("label")}
        tabIndex={0}
        className="min-h-0 flex-1 overflow-y-auto bg-ed px-3.5 py-2 font-mono text-code [overflow-wrap:anywhere] whitespace-pre-wrap focus-visible:-outline-offset-2"
        onScroll={(event) => {
          const element = event.currentTarget;
          // Scrolled up by the user, not clamped by shorter output.
          if (element.scrollTop < lastTop.current && !atBottom(element)) setFollow(false);
          lastTop.current = element.scrollTop;
        }}
      >
        {lines.length === 0 && live.length === 0 && <div className="text-mu">{empty}</div>}
        {/* The console only grows: a line keeps its index. */}
        {lines.map((line, index) => (
          <Row key={index} line={line} isLink={isLink} onLink={onLink} />
        ))}
        {live.map((line, index) => (
          <Row key={`live-${index}`} line={line} isLink={isLink} onLink={onLink} />
        ))}
      </div>
      <div className="flex h-10 flex-none items-center gap-2 border-t border-bd bg-sf px-2.5">
        <Button variant="ghost" disabled={lines.length === 0} onClick={() => void copy()}>
          <Copy aria-hidden="true" />
          {t("copy")}
        </Button>
        <div className="flex-1" />
        <label className="flex cursor-pointer items-center gap-2 text-caption text-mu">
          {t("follow")}
          <Switch
            checked={follow}
            onCheckedChange={(checked) => (checked ? toBottom() : setFollow(false))}
          />
        </label>
        <Button onClick={toBottom}>
          <ArrowDown aria-hidden="true" />
          {t("bottom")}
        </Button>
      </div>
    </div>
  );
}
