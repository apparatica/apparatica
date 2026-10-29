"use client";

// The code editor of a problem page (FR-EDT-01): Monaco with the themes of the design, following
// the theme on screen, and the diagnostics of the last check as markers (FR-EDT-05): a squiggle,
// an icon in the margin and a tinted line, so not by colour alone. Loaded lazily and only in the
// browser (`next/dynamic`, NFR-PERF-06).
import Editor from "@monaco-editor/react";
import type { editor } from "monaco-editor/editor";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { useResolvedTheme } from "@/components/shell/theme";
import type { Schemas } from "@/lib/api/client";

import { monaco } from "./monaco";
import { monacoTheme } from "./themes";

export type Diagnostic = Schemas["Diagnostic"];

const MARKER_OWNER = "apparatica";

const SEVERITIES: Record<Diagnostic["severity"], monaco.MarkerSeverity> = {
  error: monaco.MarkerSeverity.Error,
  warning: monaco.MarkerSeverity.Warning,
  info: monaco.MarkerSeverity.Info,
};

/** A marker of a diagnostic; without a column it spans the line. */
function markerOf(model: editor.ITextModel, diagnostic: Diagnostic): editor.IMarkerData {
  const line = Math.min(diagnostic.line ?? 1, model.getLineCount());
  const column = diagnostic.col ?? 1;
  const endLine = diagnostic.end_line ?? line;
  const endColumn =
    diagnostic.end_col ?? (diagnostic.col == null ? model.getLineMaxColumn(line) : column);
  return {
    severity: SEVERITIES[diagnostic.severity],
    message: diagnostic.message,
    ...(diagnostic.code == null ? {} : { code: diagnostic.code }),
    startLineNumber: line,
    startColumn: column,
    endLineNumber: endLine,
    endColumn,
  };
}

/** The margin icon and the tint of the line of a diagnostic (styles in globals.css). */
function decorationOf(diagnostic: Diagnostic): editor.IModelDeltaDecoration {
  const line = diagnostic.line ?? 1;
  return {
    range: new monaco.Range(line, 1, line, 1),
    options: {
      isWholeLine: true,
      className: `apx-line-${diagnostic.severity}`,
      glyphMarginClassName: `apx-glyph apx-glyph-${diagnostic.severity}`,
      glyphMarginHoverMessage: { value: diagnostic.message },
      stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
    },
  };
}

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
  // The default is "dimmed" on Linux only: the number of the empty last line at 40% opacity fails
  // the AA contrast (NFR-A11Y-01). "on" renders it like the others on every OS.
  renderFinalNewline: "on",
  // Always there, so that the first diagnostic does not shift the code.
  glyphMargin: true,
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
  /** Diagnostics of the code, shown as markers; each has a line. */
  markers: readonly Diagnostic[];
  onMount: (editor: editor.IStandaloneCodeEditor) => void;
}

export default function CodeEditor({
  defaultValue,
  language,
  path,
  label,
  loading,
  markers,
  onMount,
}: CodeEditorProps) {
  const theme = useResolvedTheme();
  const [instance, setInstance] = useState<editor.IStandaloneCodeEditor | null>(null);
  // The markers shown: a check event that does not change them leaves them (and their hover) be.
  const shown = useRef<{ key: string; lines: editor.IEditorDecorationsCollection } | null>(null);

  useEffect(() => {
    const model = instance?.getModel();
    if (instance == null || model == null) return;
    const key = JSON.stringify(markers);
    if (shown.current?.key === key) return;
    shown.current?.lines.clear();
    monaco.editor.setModelMarkers(
      model,
      MARKER_OWNER,
      markers.map((diagnostic) => markerOf(model, diagnostic)),
    );
    shown.current = { key, lines: instance.createDecorationsCollection(markers.map(decorationOf)) };
  }, [instance, markers]);

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
        shown.current = null;
        setInstance(instance);
        onMount(instance);
      }}
    />
  );
}
