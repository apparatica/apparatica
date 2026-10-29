// The Monaco themes of the design: brief/apparatica-handoff/design/monaco-themes.ts, the same
// values as the code tokens of tokens.css (--kw, --ty, --nm, --cm, --fn). Change them only together
// with the design. Two rules are added to the handoff: the Monarch grammar of SystemVerilog writes
// `$display` as `variable.predefined` and every keyword as `keyword.<word>`, so the system tasks and
// the data types get the colours the statements give them (src/lib/statement/highlight.ts).
import type { editor } from "monaco-editor/editor";

import type { ResolvedTheme } from "@/lib/theme";

/** Keywords that name a data type: coloured as types, like Shiki does in the statements. */
const TYPE_KEYWORDS = [
  "bit",
  "byte",
  "int",
  "integer",
  "logic",
  "longint",
  "real",
  "reg",
  "shortint",
  "shortreal",
  "string",
  "time",
];

interface Palette {
  keyword: string;
  type: string;
  number: string;
  comment: string;
  predefined: string;
  identifier: string;
  delimiter: string;
}

function rules(palette: Palette): editor.ITokenThemeRule[] {
  return [
    { token: "keyword", foreground: palette.keyword },
    { token: "type", foreground: palette.type },
    ...TYPE_KEYWORDS.map((word) => ({ token: `keyword.${word}`, foreground: palette.type })),
    { token: "number", foreground: palette.number },
    { token: "string", foreground: palette.number },
    { token: "comment", foreground: palette.comment, fontStyle: "italic" },
    { token: "predefined", foreground: palette.predefined },
    { token: "variable.predefined", foreground: palette.predefined },
    { token: "identifier", foreground: palette.identifier },
    { token: "delimiter", foreground: palette.delimiter },
  ];
}

const benchLight: editor.IStandaloneThemeData = {
  base: "vs",
  inherit: false,
  rules: rules({
    keyword: "0e7490",
    type: "6d28d9",
    number: "a24b0a",
    comment: "5a665c",
    predefined: "1d4ed8",
    identifier: "141a15",
    delimiter: "505a52",
  }),
  colors: {
    "editor.background": "#fbfcf9",
    "editor.foreground": "#141a15",
    // --sf, not --sf2 of the mock-up: keywords (--ac) on it keep the AA contrast (NFR-A11Y-01).
    "editor.lineHighlightBackground": "#f6f7f3",
    "editor.selectionBackground": "#e0f1f5",
    "editorLineNumber.foreground": "#505a52",
    "editorLineNumber.activeForeground": "#141a15",
    "editorCursor.foreground": "#0e7490",
    "editorIndentGuide.background1": "#c3c9bf",
    "editorError.foreground": "#b42318",
    "editorWarning.foreground": "#7a4f00",
  },
};

const benchDark: editor.IStandaloneThemeData = {
  base: "vs-dark",
  inherit: false,
  rules: rules({
    keyword: "22d3ee",
    type: "c4b5fd",
    number: "fbbf24",
    comment: "7d887e",
    predefined: "86efac",
    identifier: "dfe6df",
    delimiter: "8f9b92",
  }),
  colors: {
    "editor.background": "#090c0a",
    "editor.foreground": "#dfe6df",
    "editor.lineHighlightBackground": "#151a17",
    "editor.selectionBackground": "#0b2a31",
    "editorLineNumber.foreground": "#8f9b92",
    "editorLineNumber.activeForeground": "#dfe6df",
    "editorCursor.foreground": "#22d3ee",
    "editorIndentGuide.background1": "#222a25",
    "editorError.foreground": "#ff7b72",
    "editorWarning.foreground": "#e3b341",
  },
};

export const MONACO_THEMES: Record<`bench-${ResolvedTheme}`, editor.IStandaloneThemeData> = {
  "bench-light": benchLight,
  "bench-dark": benchDark,
};

export const monacoTheme = (theme: ResolvedTheme) => `bench-${theme}` as const;
