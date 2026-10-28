// Monaco for the problem page, bundled with the app (no CDN, so the CSP stays strict): the editor
// with the features a solution needs, the SystemVerilog grammar, the themes of the design and the
// worker. Loaded lazily together with the editor (NFR-PERF-06), never on the server.
import "monaco-editor/features/bracketMatching/register";
import "monaco-editor/features/caretOperations/register";
import "monaco-editor/features/clipboard/register";
import "monaco-editor/features/codicon/register";
import "monaco-editor/features/comment/register";
import "monaco-editor/features/contextmenu/register";
import "monaco-editor/features/cursorUndo/register";
import "monaco-editor/features/find/register";
import "monaco-editor/features/folding/register";
import "monaco-editor/features/gotoError/register";
import "monaco-editor/features/hover/register";
import "monaco-editor/features/indentation/register";
import "monaco-editor/features/lineSelection/register";
import "monaco-editor/features/linesOperations/register";
import "monaco-editor/features/multicursor/register";
import "monaco-editor/features/smartSelect/register";
import "monaco-editor/features/snippet/register";
import "monaco-editor/features/suggest/register";
import "monaco-editor/features/toggleTabFocusMode/register";
import "monaco-editor/features/unicodeHighlighter/register";
import "monaco-editor/features/wordHighlighter/register";
import "monaco-editor/features/wordOperations/register";
import "monaco-editor/languages/definitions/systemverilog/register";

import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor";

import { MONACO_THEMES } from "./themes";

self.MonacoEnvironment = {
  getWorker: () => new Worker(new URL("./editor.worker.ts", import.meta.url), { type: "module" }),
};

for (const [name, theme] of Object.entries(MONACO_THEMES)) monaco.editor.defineTheme(name, theme);

loader.config({ monaco });

export { monaco };
