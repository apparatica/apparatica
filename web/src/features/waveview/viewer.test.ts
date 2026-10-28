import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeAdapter } from "@/test/waveview";

import { READY_TIMEOUT_MS, type TraceView, Viewer } from "./viewer";

let frame: HTMLIFrameElement;

beforeEach(() => {
  frame = document.createElement("iframe");
  document.body.append(frame);
});

afterEach(() => {
  frame.remove();
  vi.useRealTimers();
});

const trace = (key = "a"): TraceView => ({
  key,
  bytes: new Uint8Array([1, 2, 3]).buffer,
  signals: [{ path: "tb_top.clk", color: "Clock", label: "clk" }],
  cursor: { time: 300, marker: "такт 30" },
});

const phaseOf = (viewer: Viewer) => viewer.getSnapshot().state.phase;

describe("the frame", () => {
  it("starts, hides the panels of Surfer and takes the theme", async () => {
    const viewer = new Viewer();
    viewer.setTheme("apparatica-dark");
    const adapter = fakeAdapter(frame);
    viewer.attach(frame);
    expect(phaseOf(viewer)).toBe("starting");
    adapter.ready();
    expect(phaseOf(viewer)).toBe("ready");
    await vi.waitFor(() => expect(adapter.received).toHaveLength(2));
    expect(adapter.received).toMatchObject([
      { apx: 1, type: "chrome" },
      { apx: 1, type: "theme", name: "apparatica-dark" },
    ]);
    viewer.setTheme("apparatica-light");
    await vi.waitFor(() =>
      expect(adapter.received.at(-1)).toMatchObject({ type: "theme", name: "apparatica-light" }),
    );
  });

  it("takes messages of its frame only", () => {
    const viewer = new Viewer();
    viewer.attach(frame);
    window.dispatchEvent(
      new MessageEvent("message", { data: { apx: 1, type: "ready" }, source: window }),
    );
    expect(phaseOf(viewer)).toBe("starting");
  });

  it("fails when Surfer does not start in time", () => {
    vi.useFakeTimers();
    const viewer = new Viewer();
    viewer.attach(frame);
    vi.advanceTimersByTime(READY_TIMEOUT_MS);
    expect(viewer.getSnapshot().state).toEqual({
      phase: "failed",
      message: `the viewer did not start in ${READY_TIMEOUT_MS} ms`,
    });
  });

  it("fails after a panic; a retry asks for a new frame", () => {
    const viewer = new Viewer();
    const adapter = fakeAdapter(frame);
    viewer.attach(frame);
    adapter.ready();
    adapter.say({ type: "crashed", message: "index out of bounds" });
    expect(viewer.getSnapshot()).toEqual({
      state: { phase: "failed", message: "the viewer crashed: index out of bounds" },
      frame: 0,
    });
    viewer.retry();
    expect(viewer.getSnapshot()).toEqual({ state: { phase: "starting" }, frame: 1 });
  });
});

describe("a trace", () => {
  it("loads once the viewer is up: the file, the signals, the whole window, the cursor", async () => {
    const viewer = new Viewer();
    const adapter = fakeAdapter(frame);
    const shown = trace();
    viewer.show(shown);
    viewer.attach(frame);
    adapter.ready();
    await vi.waitFor(() => expect(phaseOf(viewer)).toBe("shown"));
    expect(adapter.received.map(({ type }) => type)).toEqual([
      "chrome",
      "load",
      "signals",
      "fit",
      "cursor",
      "marker",
    ]);
    const load = adapter.received[1];
    // A copy goes: the transfer would empty the buffer of the page.
    expect(load?.["bytes"]).not.toBe(shown.bytes);
    expect(new Uint8Array(load?.["bytes"] as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    expect(adapter.received.slice(2)).toMatchObject([
      { items: shown.signals },
      {},
      { time: 300 },
      { time: 300, name: "такт 30" },
    ]);
    expect(viewer.getSnapshot().state).toEqual({ phase: "shown", key: "a" });

    viewer.show(trace());
    expect(phaseOf(viewer)).toBe("shown"); // the same file is not loaded again
    viewer.focus();
    await vi.waitFor(() =>
      expect(adapter.received.slice(6).map(({ type }) => type)).toEqual(["cursor", "center"]),
    );
  });

  it("that does not open fails the frame", async () => {
    const viewer = new Viewer();
    const adapter = fakeAdapter(frame, { fail: "load" });
    viewer.attach(frame);
    adapter.ready();
    viewer.show(trace());
    expect(phaseOf(viewer)).toBe("loading");
    await vi.waitFor(() =>
      expect(viewer.getSnapshot().state).toEqual({ phase: "failed", message: "load: load broke" }),
    );
  });

  it("replaces the shown one", async () => {
    const viewer = new Viewer();
    const adapter = fakeAdapter(frame);
    viewer.attach(frame);
    adapter.ready();
    viewer.show(trace("a"));
    await vi.waitFor(() => expect(phaseOf(viewer)).toBe("shown"));
    viewer.show(trace("b"));
    await vi.waitFor(() =>
      expect(viewer.getSnapshot().state).toEqual({ phase: "shown", key: "b" }),
    );
    expect(adapter.received.filter(({ type }) => type === "load")).toHaveLength(2);
  });
});
