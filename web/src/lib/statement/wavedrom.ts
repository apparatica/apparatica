// ```wavedrom blocks of a statement as inline SVG, rendered on the server. The source is the
// WaveDrom object (JSON5: unquoted keys and trailing commas allowed). The SVG of WaveDrom is
// made to live next to others on a page: its global <style> is dropped (the styles of its classes
// go inline, with the design tokens), colours become tokens, and ids get a prefix per diagram.
import type { Element, Root } from "hast";
import { fromHtml } from "hast-util-from-html";
import JSON5 from "json5";
import { visit } from "unist-util-visit";
import type { VFile } from "vfile";
import { onml, type Onml, renderAny, waveSkin } from "wavedrom";

import { codeLanguage, textOf } from "./hast";

// Colours that WaveDrom writes in attributes and inline styles, as tokens.
const COLOURS: [RegExp, string][] = [
  [/fill:\s*white/gi, "fill:none"], // the background
  [/#fff\b|#ffffff\b/gi, "var(--sf)"], // behind the labels of arcs
  [/#000\b|#000000\b/gi, "var(--tx)"],
  [/#888\b/gi, "var(--bd)"], // the grid
  [/#0041c4\b/gi, "var(--ac)"], // arcs
];

function recolour(value: string): string {
  return COLOURS.reduce((text, [pattern, token]) => text.replace(pattern, token), value);
}

// The classes of the WaveDrom skin as inline styles with the tokens. Most shapes are drawn through
// <use>, and the copies <use> makes do not match the selectors of a stylesheet reliably: the style
// travels with the element instead.
const LINE = "fill:none;stroke:var(--mu);stroke-linecap:round";
const AREA = (token: string) => `fill:var(${token});stroke:none`;
const CLASS_STYLES: Record<string, string> = {
  s1: `${LINE};stroke-width:1`,
  s2: `${LINE};stroke-width:0.5`,
  s3: `${LINE};stroke-width:1;stroke-dasharray:1,3`,
  s4: `${LINE};stroke-width:1`,
  s5: AREA("--ed"),
  s6: AREA("--mu"),
  s7: AREA("--ed"),
  // Data colours 3–9.
  s8: AREA("--wns"),
  s9: AREA("--ers"),
  s10: AREA("--ins"),
  s11: AREA("--acs"),
  s12: AREA("--oks"),
  s13: AREA("--hs"),
  s14: AREA("--ms"),
  s15: AREA("--ac"),
  s16: "fill:none;stroke:var(--ac);stroke-linecap:round;stroke-width:1",
  info: "fill:var(--mu)",
  muted: "fill:var(--mu)",
  warning: "fill:var(--wn)",
  error: "fill:var(--er)",
  success: "fill:var(--ok)",
};

function classStyle(classes: string): string | undefined {
  const styles = classes.split(/\s+/).flatMap((name) => CLASS_STYLES[name] ?? []);
  return styles.length > 0 ? styles.join(";") : undefined;
}

/** Without the <style>; ids, references and colours rewritten. */
function adapt(node: Onml, prefix: string): Onml | null {
  const [tag, ...rest] = node;
  if (tag === "style") return null;
  const out: Onml = [tag];
  for (const item of rest) {
    if (typeof item === "string") {
      out.push(item);
    } else if (Array.isArray(item)) {
      const child = adapt(item, prefix);
      if (child !== null) out.push(child);
    } else {
      const attributes: Record<string, string | number> = {};
      for (const [name, value] of Object.entries(item)) {
        if (typeof value !== "string") {
          attributes[name] = value;
        } else if (name === "id") {
          attributes[name] = prefix + value;
        } else if ((name === "xlink:href" || name === "href") && value.startsWith("#")) {
          attributes[name] = `#${prefix}${value.slice(1)}`;
        } else if (name === "fill" || name === "stroke") {
          // Attributes take no var(): the colour goes to the style.
          const style = `${name}:${recolour(value)}`;
          attributes.style =
            attributes.style === undefined ? style : `${attributes.style};${style}`;
        } else {
          const text = value.replaceAll("url(#", `url(#${prefix}`);
          attributes[name] = name === "style" ? recolour(text) : text;
        }
      }
      // The style of the class first: a style of the element itself wins over it.
      const fromClass =
        typeof attributes.class === "string" ? classStyle(attributes.class) : undefined;
      if (fromClass !== undefined) {
        attributes.style =
          attributes.style === undefined ? fromClass : `${fromClass};${attributes.style}`;
      }
      out.push(attributes);
    }
  }
  return out;
}

/** The SVG of a diagram; throws on a broken source. */
export function renderWaveform(source: string, index: number): Element {
  const tree = renderAny(index, JSON5.parse(source), waveSkin);
  const svg = adapt(tree, `wd${index}-`);
  if (svg === null) throw new Error("empty diagram");
  const root = fromHtml(onml.stringify(svg), { fragment: true, space: "svg" });
  const element = root.children.find((child): child is Element => child.type === "element");
  if (element === undefined) throw new Error("no SVG");
  return element;
}

export interface WaveDromOptions {
  /** The accessible name of a diagram. */
  label: string;
}

/** Replaces `<pre><code class="language-wavedrom">` with a figure of the SVG. A broken source
 * stays as code, with a message on the file. */
export function rehypeWavedrom({ label }: WaveDromOptions) {
  return (tree: Root, file: VFile) => {
    let index = 0;
    visit(tree, "element", (node, position, parent) => {
      if (node.tagName !== "pre" || parent === undefined || position === undefined) return;
      const code = node.children[0];
      if (code?.type !== "element" || codeLanguage(code) !== "wavedrom") return;
      try {
        const svg = renderWaveform(textOf(code), index++);
        svg.properties = { ...svg.properties, role: "img", ariaLabel: label };
        parent.children[position] = {
          type: "element",
          tagName: "figure",
          properties: { className: ["wavedrom"] },
          children: [svg],
          ...(node.position && { position: node.position }),
        };
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error);
        file.message(`WaveDrom: ${reason}`, { place: node.position, ruleId: "wavedrom" });
      }
    });
  };
}
