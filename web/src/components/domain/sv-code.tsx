// SystemVerilog highlighted for CodeViewer, rendered by the server with the highlighter of the
// statements (Shiki, the code tokens of the design): the page sends the coloured HTML, not the
// highlighter.
import { toJsxRuntime } from "hast-util-to-jsx-runtime";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";

import { highlightSv } from "@/lib/statement/highlight";

export function SvCode({ code }: { code: string }) {
  const pre = highlightSv(code);
  const classes = pre.properties.className;
  pre.properties.className = [...(Array.isArray(classes) ? classes : []), "code-lines"];
  return toJsxRuntime(pre, { Fragment, jsx, jsxs });
}
