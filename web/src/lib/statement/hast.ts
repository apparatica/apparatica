// Small helpers for the HTML trees of a statement.
import type { Element, ElementContent } from "hast";

/** The language of a code element: `language-sv` → `sv`. */
export function codeLanguage(code: Element): string | null {
  const classes = code.properties.className;
  if (!Array.isArray(classes)) return null;
  for (const name of classes) {
    if (typeof name === "string" && name.startsWith("language-")) return name.slice(9);
  }
  return null;
}

/** The text of a node and its children. */
export function textOf(node: ElementContent): string {
  if (node.type === "text") return node.value;
  if (node.type !== "element") return "";
  return node.children.map(textOf).join("");
}
