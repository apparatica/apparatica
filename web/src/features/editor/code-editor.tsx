"use client";

// The code editor of a problem page (FR-EDT-01): Monaco with the themes of the design, following
// the theme on screen. Loaded lazily and only in the browser (`next/dynamic`, NFR-PERF-06).
import Editor from "@monaco-editor/react";
import type { editor } from "monaco-editor/editor";
import type { ReactNode } from "react";

import { useResolvedTheme } from "@/components/shell/theme";

import { monaco } from "./monaco";
import { monacoTheme } from "./themes";

const OPTIONS: editor.IStandaloneEditorConstructionOptions = {
  fontFamily: '"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace',
  fontSize: 12.5,
  lineHeight: 19,
  fontLigatures: false,
  tabSize: 2,
  insertSpaces: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  padding: { top: 6 },
  lineNumbersMinChars: 3,
  renderLineHighlight: "line",
  automaticLayout: true,
  fixedOverflowWidgets: true,
  overviewRulerBorder: false,
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  stickyScroll: { enabled: false },
};

export interface CodeEditorProps {
  defaultValue: string;
  /** The Monaco language id. */
  language: string;
  /** The model URI path: one model per problem and file. */
  path: string;
  label: string;
  /** Shown until Monaco is ready. */
  loading: ReactNode;
  onMount: (editor: editor.IStandaloneCodeEditor) => void;
}

export default function CodeEditor({
  defaultValue,
  language,
  path,
  label,
  loading,
  onMount,
}: CodeEditorProps) {
  const theme = useResolvedTheme();
  return (
    <Editor
      defaultValue={defaultValue}
      defaultLanguage={language}
      path={path}
      theme={monacoTheme(theme)}
      options={{ ...OPTIONS, ariaLabel: label }}
      loading={loading}
      onMount={(instance) => {
        // SystemVerilog pairs module/endmodule and begin/end as brackets; the design colours them
        // as keywords, not by nesting. The model, not the editor, colours the pairs.
        instance.getModel()?.updateOptions({
          bracketColorizationOptions: { enabled: false, independentColorPoolPerBracketType: false },
        });
        // Monaco measures the font when it starts; IBM Plex Mono may arrive later.
        void document.fonts.ready.then(() => monaco.editor.remeasureFonts());
        onMount(instance);
      }}
    />
  );
}
