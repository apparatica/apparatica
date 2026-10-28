// Regression of the waveview build (ADR-0004): the FST of a demo problem, recorded with the current
// toolchain profile, opens in the built Surfer through the adapter, in an isolated frame on its own
// origin with the headers of the stand (deploy/Caddyfile). It covers the unstable Surfer messages
// the adapter uses: LoadFromData, SelectTheme, the panel switches, ItemNameChange, Batch.
//
//   WAVEVIEW_DIST=<dir with <version>/>  node --test tests/   (just waveview-test)
//   WAVEVIEW_BROWSER: Playwright channel, "chrome" by default ("msedge" on Windows)
//   WAVEVIEW_SCREENSHOTS: a directory for screenshots of both themes
import assert from "node:assert/strict";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { after, before, test } from "node:test";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

import { chromium } from "playwright-core";

import { serve } from "./serve.mjs";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const VERSION = /^WAVEVIEW_VERSION=(.+)$/m.exec(
  readFileSync(join(ROOT, "waveview", "versions.lock"), "utf8"),
)[1];
const DIST = process.env.WAVEVIEW_DIST ?? join(ROOT, "waveview", "dist");
const SCENARIO = JSON.parse(
  readFileSync(join(ROOT, "web", "src", "mocks", "scenarios", "wrong-answer.json"), "utf8"),
);
const FST = SCENARIO.files.fst;
const WAVEFORM = SCENARIO.submission.artifacts.find((a) => a.kind === "fst").waveform;
// Canvas backgrounds of the themes (themes/*.toml, tokens.css --ed).
const BACKGROUNDS = { "apparatica-light": [0xfb, 0xfc, 0xf9], "apparatica-dark": [0x09, 0x0c, 0x0a] };
const COLORS = { clock: "Clock", input: undefined, output: "Bus", expected: "Expected" };

let servers;
let browser;
let page;

const apx = (type, fields) => page.evaluate(([t, f]) => window.apx.call(t, f), [type, fields]);

before(async () => {
  assert.ok(existsSync(join(DIST, VERSION, "surfer_bg.wasm")), `no build in ${DIST}/${VERSION}`);
  servers = await serve(DIST);
  browser = await chromium.launch({ channel: process.env.WAVEVIEW_BROWSER ?? "chrome" });
  page = await browser.newPage({ viewport: { width: 900, height: 420 } });
  page.on("console", (message) => {
    if (message.type() === "error") console.error("[page]", message.text());
  });
  const viewer = `${servers.waveview}/${VERSION}/index.html`;
  await page.goto(`${servers.host}/host.html?viewer=${encodeURIComponent(viewer)}`);
});

after(async () => {
  await browser?.close();
  await servers?.close();
});

test("the viewer starts in an isolated frame", async () => {
  const ready = await page.evaluate(() => window.apx.open());
  assert.equal(ready.protocol, 1);
  // As the greeting names them (not always the names of the commands themselves).
  for (const command of ["add_variables", "set_item_color", "cursor_set", "add_markers"]) {
    assert.ok(ready.commands.includes(command), command);
  }
  const frame = page.frames().find((f) => f.url().includes(`/${VERSION}/`));
  assert.equal(await frame.evaluate(() => self.origin), "null");
  const reach = await frame.evaluate(async (host) => {
    const tries = {
      parent: () => window.parent.document.title,
      cookie: () => document.cookie,
      storage: () => localStorage.length,
      network: () => fetch(`${host}/host.html`),
    };
    const outcome = {};
    for (const [name, attempt] of Object.entries(tries)) {
      try {
        await attempt();
        outcome[name] = "reached";
      } catch {
        outcome[name] = "blocked";
      }
    }
    return outcome;
  }, servers.host);
  assert.deepEqual(reach, {
    parent: "blocked",
    cookie: "blocked",
    storage: "blocked",
    network: "blocked",
  });
});

test("a trace window opens with its signals, cursor and themes", async (t) => {
  assert.equal((await apx("chrome", {})).type, "ack");
  const loaded = await apx("load", { bytes: FST });
  assert.equal(loaded.type, "loaded", loaded.message);

  const items = WAVEFORM.signals.map(({ path, port, role }) => ({
    path,
    color: COLORS[role],
    label: role === "expected" ? `${port} ожидалось` : port,
  }));
  const signals = await apx("signals", { items });
  assert.equal(signals.type, "ack", signals.message);
  // Every signal the judge names is in the FST (the naming rule of the testbench).
  assert.deepEqual(signals.added, items.map((item) => item.path));
  assert.deepEqual((await apx("signals", { items: [{ path: "tb_top.no_such" }] })).added, []);

  const cursor = WAVEFORM.cursor_time_ps;
  for (const [type, fields] of [
    ["fit", {}],
    ["cursor", { time: cursor }],
    ["marker", { time: cursor, name: `такт ${WAVEFORM.cursor_cycle}` }],
    ["center", { time: cursor }],
    ["range", { from: 0, to: cursor * 2 }],
  ]) {
    const reply = await apx(type, fields);
    assert.equal(reply.type, "ack", `${type}: ${reply.message}`);
  }
  assert.equal((await apx("cursor", { time: -1 })).type, "error");

  for (const theme of Object.keys(BACKGROUNDS)) {
    await t.test(theme, async () => {
      assert.equal((await apx("theme", { name: theme })).type, "ack");
      await page.waitForTimeout(300); // the next frame of Surfer
      const pixel = await backgroundPixel(theme);
      assert.deepEqual(pixel, BACKGROUNDS[theme], `canvas background of ${theme}`);
    });
  }
  assert.equal((await apx("theme", { name: "dark+" })).type, "error"); // ours only
});

test("a broken file fails the load, not the page", async () => {
  const garbage = Buffer.from(Array.from({ length: 4096 }, (_, i) => (i * 7919) % 251)).toString(
    "base64",
  );
  const reply = await apx("load", { bytes: garbage, timeoutMs: 3000 });
  // Surfer reports a parse error only to its log (a timeout here) or panics (crashed).
  const crashed = await page.evaluate(() => window.apx.unprompted("crashed", 500).catch(() => null));
  assert.ok(reply.type === "error" || crashed !== null, JSON.stringify(reply));
  // A new frame works again.
  assert.equal((await page.evaluate(() => window.apx.open())).protocol, 1);
  assert.equal((await apx("load", { bytes: FST })).type, "loaded");
});

/** The colour of the empty waves area near the bottom right corner, after a screenshot. */
async function backgroundPixel(theme) {
  const box = await page.locator("iframe").boundingBox();
  const shots = process.env.WAVEVIEW_SCREENSHOTS;
  if (shots) {
    mkdirSync(shots, { recursive: true });
    await page.screenshot({ path: join(shots, `${theme}.png`), clip: box });
  }
  const png = await page.screenshot({
    clip: { x: box.x + box.width - 8, y: box.y + box.height - 8, width: 1, height: 1 },
  });
  return pixelOf(png);
}

/** RGB of a 1×1 PNG: with no neighbours every filter leaves the bytes as they are. */
function pixelOf(png) {
  let offset = 8;
  let channels = 3;
  const data = [];
  while (offset < png.length) {
    const length = png.readUInt32BE(offset);
    const type = png.toString("ascii", offset + 4, offset + 8);
    const body = png.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") channels = body[9] === 6 ? 4 : 3;
    if (type === "IDAT") data.push(body);
    offset += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(data));
  assert.equal(raw.length, 1 + channels);
  return [raw[1], raw[2], raw[3]];
}
