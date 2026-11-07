"use client";

// Code to read (components.md «Просмотр кода», sheet CmpC; mock-up Solution): a header with the
// file name, «только чтение», the language and the number of lines, and «Копировать» on the right;
// numbered lines below. The numbers are mono in --mu and are not copied. A copy says «Код
// скопирован» in a notification that goes by itself. The highlighted lines come from the server
// (`SvCode`), so the page sends no highlighter; without them the lines are plain.
import { Copy, Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

import { CodeLines } from "./code-lines";

export interface CodeViewerProps {
  /** "sync_fifo.sv". */
  fileName: string;
  /** What «Копировать» copies and the lines are counted of. */
  code: string;
  /** "SystemVerilog"; without it the header shows the lines only. */
  language?: string | undefined;
  /** The highlighted lines (`SvCode`); plain lines without them. */
  children?: ReactNode;
  className?: string;
}

/** The lines of a text: a final line break ends the last line, it starts no new one. */
export const lineCount = (code: string): number => code.replace(/\n$/, "").split("\n").length;

export function CodeViewer({ fileName, code, language, children, className }: CodeViewerProps) {
  const t = useTranslations("domain.code");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      notify({ tone: "ok", title: t("copied") });
    } catch {
      notify({ tone: "er", title: t("copyFailed") });
    }
  };
  const lines = t("lines", { count: lineCount(code) });
  return (
    <section
      aria-label={fileName}
      className={cn("flex min-w-0 flex-col overflow-hidden rounded-md border border-bd", className)}
    >
      <header className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 border-b border-bd bg-sf px-3 py-1.5">
        <span className="font-mono text-[12.5px]">{fileName}</span>
        <span className="inline-flex items-center gap-1 rounded-sm border border-bd px-1.5 font-mono text-[11px] leading-[18px] text-mu">
          <Lock size={11} aria-hidden="true" />
          {t("readOnly")}
        </span>
        <span className="flex-1" />
        <span className="font-mono text-caption text-mu">
          {language === undefined ? lines : `${language} · ${lines}`}
        </span>
        <Button variant="ghost" onClick={() => void copy()}>
          <Copy aria-hidden="true" />
          {t("copy")}
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto bg-ed py-2">
        {children ?? <CodeLines code={code} />}
      </div>
    </section>
  );
}
