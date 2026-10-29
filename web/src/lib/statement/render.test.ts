import { toHtml } from "hast-util-to-html";
import { expect, it } from "vitest";

import { renderStatement } from "./render";
import { renderWaveform } from "./wavedrom";

const render = (markdown: string, assetUrl?: (path: string) => string) =>
  renderStatement(markdown, { waveformLabel: "Диаграмма", assetUrl });
const reasons = (markdown: string) =>
  render(markdown).messages.map((message) => `${message.line}:${message.reason}`);

it("reports what does not render, with its line", () => {
  expect(reasons("Текст\n\n$\\frac{1}{$\n")).toEqual([
    expect.stringMatching(/^3:KaTeX: KaTeX parse error: .*expected '\}'/),
  ]);
  expect(reasons("```wavedrom\n{signal: [\n```\n")).toEqual([
    expect.stringMatching(/^1:WaveDrom: JSON5: invalid end of input/),
  ]);
  expect(reasons("$x^2$, $$y$$, [a](https://x.org) ![p](assets/p.png)")).toEqual([]);
});

it("takes a paragraph of one $$ formula for a display formula", () => {
  const html = toHtml(render("$$a + b$$\n\nи $$c$$ в тексте").tree);
  expect(html.match(/katex-display/g)).toHaveLength(1);
  expect(html).toContain("в тексте");
});

it("shows pictures from assets/ only", () => {
  const markdown =
    "![a](assets/a.png) ![b](./assets/dir/b.svg) ![c](https://x.org/c.png) ![d](assets/../d.png) ![e](a.png)";
  const { tree, messages, assets } = render(markdown, (path) => `/files/${path}`);
  expect(assets).toEqual(["assets/a.png", "assets/dir/b.svg"]);
  expect(messages.map((message) => message.reason)).toEqual([
    "картинка не из assets/: https://x.org/c.png",
    "картинка не из assets/: assets/../d.png",
    "картинка не из assets/: a.png",
  ]);
  const html = toHtml(tree);
  expect(html).toContain('src="/files/assets/a.png"');
  expect(html).toContain('src="/files/assets/dir/b.svg"');
  expect(html.match(/<img/g)).toHaveLength(2);
  // Without a way to serve them the pictures are left out, and that is not an error.
  const offline = render("![a](assets/a.png)");
  expect(toHtml(offline.tree)).not.toContain("<img");
  expect(offline.messages).toEqual([]);
});

it("gives the pictures by the names of their files", () => {
  const markdown = "![a](<assets/схема 1.svg>) ![b](assets/%D0%B0.png) ![c](assets/%2e%2e/c.png)";
  const { messages, assets } = render(markdown, (path) => path);
  expect(assets).toEqual(["assets/схема 1.svg", "assets/а.png"]);
  expect(messages.map((message) => message.reason)).toEqual([
    "картинка не из assets/: assets/%2e%2e/c.png",
  ]);
});

it("highlights the SystemVerilog fences only", () => {
  const html = toHtml(render("```sv\nmodule m;\nendmodule\n```\n\n```text\nmodule\n```").tree);
  expect(html.match(/class="shiki/g)).toHaveLength(1);
  expect(html).toContain('<span style="color:var(--kw)">module</span>');
  expect(html).toContain('<code class="language-text">module\n</code>');
});

it("draws a diagram with its own ids and the colours of the theme", () => {
  const first = toHtml(renderWaveform("{signal: [{name: 'a', wave: '01'}], edge: []}", 0));
  const second = toHtml(renderWaveform("{signal: [{name: 'a', wave: '10'}]}", 1));
  expect(first).toContain('id="wd0-pclk"');
  expect(first).toContain('href="#wd0-');
  expect(second).toContain('id="wd1-pclk"');
  expect(first).not.toMatch(/<style|#000|#fff\b|white/i);
  // The classes of the skin travel as styles: <use> copies them.
  expect(first).toContain('class="s1" style="fill:none;stroke:var(--mu)');
});
