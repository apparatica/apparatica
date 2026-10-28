// Highlighting of SystemVerilog code blocks with Shiki, on the server and synchronously (the
// JavaScript regex engine). The colours are the code tokens of the design (--kw, --ty, ...), as in
// the Monaco themes, so one tree serves both themes.
import type { Element, Root } from "hast";
import { createHighlighterCoreSync, type ThemeRegistrationRaw } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import systemVerilog from "shiki/langs/system-verilog.mjs";
import { visit } from "unist-util-visit";

import { codeLanguage, textOf } from "./hast";

/** Fence languages highlighted as SystemVerilog. */
export const SV_LANGUAGES = new Set(["systemverilog", "sv", "verilog", "v", "svh"]);

const THEME: ThemeRegistrationRaw = {
  name: "apparatica",
  type: "light",
  settings: [
    { settings: { foreground: "var(--tx)", background: "var(--ed)" } },
    {
      scope: ["keyword.control", "storage.type.net", "support.type.direction", "storage.modifier"],
      settings: { foreground: "var(--kw)" },
    },
    { scope: ["storage.type", "support.type"], settings: { foreground: "var(--ty)" } },
    { scope: ["constant.numeric", "string"], settings: { foreground: "var(--nm)" } },
    { scope: ["comment"], settings: { foreground: "var(--cm)", fontStyle: "italic" } },
    { scope: ["support.function"], settings: { foreground: "var(--fn)" } },
    { scope: ["keyword.operator", "punctuation"], settings: { foreground: "var(--mu)" } },
  ],
};

let highlighter: ReturnType<typeof createHighlighterCoreSync> | null = null;

function getHighlighter() {
  highlighter ??= createHighlighterCoreSync({
    themes: [THEME],
    langs: [systemVerilog],
    engine: createJavaScriptRegexEngine(),
  });
  return highlighter;
}

/** The `<pre>` of highlighted SystemVerilog code. */
export function highlightSv(code: string): Element {
  const root = getHighlighter().codeToHast(code.replace(/\n$/, ""), {
    lang: "system-verilog",
    theme: THEME.name ?? "",
  });
  const pre = root.children[0];
  if (pre?.type !== "element") throw new Error("no <pre> from the highlighter");
  // The background and the colour come from statement.css.
  delete pre.properties.style;
  delete pre.properties.tabindex;
  return pre;
}

/** Replaces `<pre><code class="language-sv">` (and the other SV fences) with highlighted code. */
export function rehypeHighlightSv() {
  return (tree: Root) => {
    visit(tree, "element", (node, position, parent) => {
      if (node.tagName !== "pre" || parent === undefined || position === undefined) return;
      const code = node.children[0];
      const language = code?.type === "element" ? codeLanguage(code) : null;
      if (code?.type !== "element" || language === null || !SV_LANGUAGES.has(language)) return;
      const pre = highlightSv(textOf(code));
      parent.children[position] = { ...pre, ...(node.position && { position: node.position }) };
    });
  };
}
