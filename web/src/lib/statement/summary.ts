// A plain-text summary of a statement for the meta description and the link previews
// (FR-PRB-04): the text of its first paragraph, code and formulas as they are written.
import type { Nodes, Paragraph } from "mdast";
import remarkMath from "remark-math";
import remarkParse from "remark-parse";
import { unified } from "unified";

const MAX_LENGTH = 200;

function plain(node: Nodes): string {
  if (node.type === "text" || node.type === "inlineCode" || node.type === "inlineMath") {
    return node.value;
  }
  return "children" in node ? node.children.map((child) => plain(child as Nodes)).join("") : "";
}

/** The first paragraph as one line, cut at a word to `MAX_LENGTH` characters with "…". */
export function statementSummary(markdown: string, maxLength = MAX_LENGTH): string {
  const tree = unified().use(remarkParse).use(remarkMath).parse(markdown);
  const first = tree.children.find((node): node is Paragraph => node.type === "paragraph");
  const text = first === undefined ? "" : plain(first).replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  let cut = text.slice(0, maxLength - 1);
  // A word cut in the middle goes, unless it is the only one.
  const space = cut.lastIndexOf(" ");
  if (text[cut.length] !== " " && space > maxLength / 2) cut = cut.slice(0, space);
  return `${cut.replace(/[\s,;:—-]+$/, "")}…`;
}
