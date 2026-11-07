"use client";

// Two versions of a solution side by side, read-only (FR-REF-02): Monaco's diff view with the
// themes of the design, following the theme on screen. A narrow window shows the changes inline.
// Loaded lazily and only in the browser (`next/dynamic`, NFR-PERF-06), like the editor.
import { DiffEditor } from "@monaco-editor/react";
import type { ReactNode } from "react";

import { useResolvedTheme } from "@/components/shell/theme";

import "./monaco";
import { monacoTheme } from "./themes";

export interface DiffViewerProps {
  /** On the left: the own code. */
  original: string;
  /** On the right: the code compared with. */
  modified: string;
  /** The Monaco language id. */
  language: string;
  /** Names of both sides for screen readers. */
  label: string;
  /** Shown until Monaco is ready. */
  loading: ReactNode;
}

export default function DiffViewer({
  original,
  modified,
  language,
  label,
  loading,
}: DiffViewerProps) {
  const theme = useResolvedTheme();
  return (
    <DiffEditor
      original={original}
      modified={modified}
      language={language}
      theme={monacoTheme(theme)}
      loading={loading}
      options={{
        readOnly: true,
        originalEditable: false,
        domReadOnly: true,
        ariaLabel: label,
        renderSideBySide: true,
        useInlineViewWhenSpaceIsLimited: true,
        renderOverviewRuler: false,
        fontFamily: '"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace',
        fontSize: 12.5,
        lineHeight: 19,
        fontLigatures: false,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        lineNumbersMinChars: 3,
        renderLineHighlight: "none",
        automaticLayout: true,
        stickyScroll: { enabled: false },
      }}
    />
  );
}
