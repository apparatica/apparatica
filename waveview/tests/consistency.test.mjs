// What must agree without a build: the themes with the palette of the site (FR-WAV-04), and the
// version of the build with the stand that publishes it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const read = (...path) => readFileSync(join(ROOT, ...path), "utf8");

/** `--name: #hex;` of a block of tokens.css that starts with `selector`. */
function tokens(selector) {
  const css = read("web", "src", "styles", "tokens.css");
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, selector);
  const block = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*#([0-9a-f]{6});/g)].map(([, name, hex]) => [name, hex]),
  );
}

/** `key = "hex"` and `key = { color = "hex" }` of a theme. */
function theme(name) {
  const toml = read("waveview", "themes", `${name}.toml`);
  const value = (key) =>
    new RegExp(`^${key} = (?:"([0-9a-f]{6})"|\\{ color = "([0-9a-f]{6})")`, "m")
      .exec(toml)
      ?.slice(1)
      .find(Boolean);
  return {
    background: /canvas_colors = \{ background = "([0-9a-f]{6})"/.exec(toml)?.[1],
    foreground: value("foreground"),
    cursor: value("cursor"),
    clock: /^Clock = "([0-9a-f]{6})"/m.exec(toml)?.[1],
    bus: /^Bus = "([0-9a-f]{6})"/m.exec(toml)?.[1],
  };
}

for (const [name, selector] of [
  ["apparatica-light", ':root[data-theme="light"]'],
  ["apparatica-dark", ':root[data-theme="dark"]'],
]) {
  test(`${name} follows the palette`, () => {
    const palette = tokens(selector);
    // Background ed, lines tx, clock ac, buses in, cursor er (FR-WAV-04, components.md).
    assert.deepEqual(theme(name), {
      background: palette.ed,
      foreground: palette.tx,
      cursor: palette.er,
      clock: palette.ac,
      bus: palette.in,
    });
  });
}

test("the stand publishes this version", () => {
  const version = /^WAVEVIEW_VERSION=(.+)$/m.exec(read("waveview", "versions.lock"))[1];
  const compose = read("deploy", "compose.yaml");
  const named = [...compose.matchAll(/waveview:([\d.]+)\}|WAVEVIEW_VERSION: ([\d.]+)/g)].map(
    (match) => match[1] ?? match[2],
  );
  assert.deepEqual(named, [version, version]);
});
