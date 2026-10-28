// A statement from Markdown to an HTML tree (FR-PRB-03): GFM, KaTeX formulas, WaveDrom diagrams,
// highlighted SystemVerilog, pictures from assets/. HTML in the Markdown is sanitised before the
// renderers add their own markup. Synchronous, so the server renders it in one pass and the
// checker of `judge validate` (scripts/statement-check.ts) runs the same code.
import type { Element, Root } from "hast";
import type { Root as MdastRoot } from "mdast";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema, type Options as SanitizeSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";
import { visit } from "unist-util-visit";
import { VFile } from "vfile";

import { rehypeHighlightSv } from "./highlight";
import { rehypeWavedrom } from "./wavedrom";

/** Pictures of a statement live in the package, under assets/. */
function isAsset(path: string): boolean {
  const parts = path.split("/");
  return (
    parts.length > 1 &&
    parts[0] === "assets" &&
    parts.every((part) => part !== "" && part !== "." && part !== "..") &&
    !/[?#\\]/.test(path)
  );
}

export interface StatementOptions {
  /** The URL of a picture of the package, `assets/…`; without it pictures are left out. */
  assetUrl?: ((path: string) => string) | undefined;
  /** The accessible name of a timing diagram. */
  waveformLabel: string;
}

export interface RenderedStatement {
  tree: Root;
  /** Problems to fix in the statement: KaTeX, WaveDrom, pictures. */
  messages: VFile["messages"];
  /** The pictures it shows, `assets/…`. */
  assets: string[];
}

// GitHub's schema, plus the classes remark-math gives formulas for rehype-katex.
const schema: SanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
  },
};

/** A paragraph of one `$$…$$` formula is a display formula, as authors write it; remark-math
 * takes only `$$` on lines of their own for one. */
function remarkDisplayMath() {
  return (tree: MdastRoot, file: VFile) => {
    const source = String(file.value);
    tree.children = tree.children.map((node) => {
      if (node.type !== "paragraph" || node.children.length !== 1) return node;
      const [math] = node.children;
      const start = math?.position?.start.offset;
      if (math?.type !== "inlineMath" || start === undefined) return node;
      if (!source.startsWith("$$", start)) return node;
      // The markup remark-math gives a display formula.
      const code: Element = {
        type: "element",
        tagName: "code",
        properties: { className: ["language-math", "math-display"] },
        children: [{ type: "text", value: math.value }],
        ...(node.position && { position: node.position }),
      };
      return {
        type: "math",
        value: math.value,
        data: { hName: "pre", hChildren: [code] },
        ...(node.position && { position: node.position }),
      };
    });
  };
}

/** Pictures from assets/ through `assetUrl`, others left out; outside links in a new tab. */
function rehypeLinks(options: StatementOptions, assets: string[]) {
  return (tree: Root, file: VFile) => {
    visit(tree, "element", (node: Element, position, parent) => {
      if (node.tagName === "a" && typeof node.properties.href === "string") {
        if (/^https?:\/\//i.test(node.properties.href)) {
          node.properties.target = "_blank";
          node.properties.rel = ["noopener", "noreferrer", "nofollow"];
        }
        return;
      }
      if (node.tagName !== "img" || parent === undefined || position === undefined) return;
      const src = String(node.properties.src ?? "").replace(/^\.\//, "");
      if (isAsset(src)) {
        assets.push(src);
        if (options.assetUrl !== undefined) {
          node.properties.src = options.assetUrl(src);
          node.properties.loading = "lazy";
          return;
        }
      } else {
        file.message(`картинка не из assets/: ${src || "(пусто)"}`, {
          place: node.position,
          ruleId: "image",
        });
      }
      parent.children.splice(position, 1);
      return position;
    });
  };
}

export function renderStatement(markdown: string, options: StatementOptions): RenderedStatement {
  const assets: string[] = [];
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkMath)
    .use(remarkDisplayMath)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSanitize, schema)
    .use(rehypeKatex, { strict: "ignore", errorColor: "var(--er)" })
    .use(rehypeWavedrom, { label: options.waveformLabel })
    .use(rehypeHighlightSv)
    .use(rehypeLinks, options, assets);
  const file = new VFile({ value: markdown });
  const tree = processor.runSync(processor.parse(file), file) as Root;
  const messages = file.messages.map((message) => {
    // rehype-katex reports "Could not render math"; the reason is in the cause.
    if (message.source === "rehype-katex" && message.cause instanceof Error) {
      message.reason = `KaTeX: ${message.cause.message}`;
    }
    return message;
  });
  return { tree, messages, assets };
}
