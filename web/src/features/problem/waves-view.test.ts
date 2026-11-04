import { describe, expect, it } from "vitest";

import type { Submission } from "@/features/submission/machine";
import type { Schemas } from "@/lib/api/client";
import versions from "@/mocks/problem-versions.json";
import { type ScenarioName, scenarios } from "@/mocks/scenarios";
import { eventsUntil, playCheck } from "@/test/checks";

import { canTraceWholeTest, signalItems, tracedTest, wavesView } from "./waves-view";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];
const VIEWER = "https://waveview.test/2026.10.1/index.html";
const MB = 1024 * 1024;

/** The stored submission of a scenario, with its FST changed. */
function stored(name: ScenarioName, fst: Partial<Schemas["SubmissionArtifact"]> = {}): Submission {
  const { submission } = scenarios[name];
  return {
    ...submission,
    waveview_url: VIEWER,
    artifacts: submission.artifacts.map((artifact) =>
      artifact.kind === "fst" ? { ...artifact, ...fst } : artifact,
    ),
  };
}

const view = (name: ScenarioName, submission: Submission | null = stored(name), max = 5 * MB) =>
  wavesView(playCheck(scenarios[name]), submission, max);

describe("the trace", () => {
  it("of a failed open test is shown in the viewer", () => {
    const shown = view("wrong-answer");
    expect(shown).toMatchObject({
      kind: "ready",
      viewerUrl: VIEWER,
      trace: { stage: "sim_run", test: "заполнение до full и опустошение" },
    });
    expect(tracedTest(shown)).toBe("t2");
  });

  it("waits for the stored submission after the check", () => {
    const { submission } = scenarios["wrong-answer"];
    expect(view("wrong-answer", null)).toEqual({ kind: "waiting" });
    expect(view("wrong-answer", { ...submission, finished_at: null })).toEqual({
      kind: "waiting",
    });
  });

  it("follows the state of the file", () => {
    expect(view("wrong-answer", stored("wrong-answer", { state: "expired" })).kind).toBe("expired");
    expect(
      view("wrong-answer", stored("wrong-answer", { state: "pending", size_bytes: null })).kind,
    ).toBe("pending");
    expect(view("wrong-answer", stored("wrong-answer", { state: "failed" })).kind).toBe("failed");
    expect(view("wrong-answer", { ...stored("wrong-answer"), waveview_url: null }).kind).toBe(
      "noViewer",
    );
  });

  it("of the whole test is its own FST, asked for once", () => {
    const check = playCheck(scenarios["wrong-answer"]);
    const submission = stored("wrong-answer");
    expect(canTraceWholeTest(check)).toBe(true);
    const window = wavesView(check, submission, 5 * MB, "full_test");
    expect(window).toMatchObject({ kind: "unrequested", trace: { stage: "sim_run" } });

    const [fst] = submission.artifacts.filter((artifact) => artifact.kind === "fst");
    const traced = fst?.waveform;
    if (fst === undefined || traced == null) throw new Error("no trace window");
    const whole = (artifact: Partial<Schemas["SubmissionArtifact"]>) => ({
      ...submission,
      artifacts: [
        ...submission.artifacts,
        { ...fst, waveform: { ...traced, scope: "full_test" as const }, ...artifact },
      ],
    });
    expect(wavesView(check, whole({ state: "pending" }), 5 * MB, "full_test").kind).toBe("pending");
    expect(
      wavesView(check, whole({ state: "failed", error_code: "TRACE_TOO_LARGE" }), MB, "full_test"),
    ).toMatchObject({ kind: "failed", tooLarge: true });
    expect(wavesView(check, whole({ size_bytes: 9000 }), 5 * MB, "full_test")).toMatchObject({
      kind: "ready",
      trace: { waveform: { scope: "full_test" }, artifact: { size_bytes: 9000 } },
    });
    // The window stays the window.
    expect(wavesView(check, whole({ size_bytes: 9000 }), 5 * MB)).toMatchObject({
      kind: "ready",
      trace: { waveform: { scope: "failure_window" }, artifact: { size_bytes: 2491 } },
    });
  });

  it("larger than the limit is for download only", () => {
    expect(view("wrong-answer", stored("wrong-answer"), 2048)).toMatchObject({
      kind: "tooBig",
      sizeBytes: 2491,
    });
  });
});

describe("no waves", () => {
  it("while the check runs", () => {
    const scenario = scenarios["wrong-answer"];
    const check = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
    expect(wavesView(check, null, MB)).toEqual({ kind: "none", reason: "running" });
  });

  it("when no open test failed", () => {
    expect(view("accepted")).toEqual({ kind: "none", reason: "noFailure" });
    expect(view("compile-error")).toEqual({ kind: "none", reason: "noFailure" });
    expect(tracedTest(view("accepted"))).toBeNull();
  });

  it("when a hidden test failed", () => {
    expect(view("wrong-answer-hidden")).toEqual({ kind: "none", reason: "hidden" });
  });

  it("when the trace was not recorded", () => {
    const submission = stored("wrong-answer");
    const unrecorded = {
      ...submission,
      artifacts: submission.artifacts.filter((a) => a.kind !== "fst"),
    };
    expect(view("wrong-answer", unrecorded)).toEqual({ kind: "none", reason: "notRecorded" });
  });
});

it("orders the signals as the judge does, buses and the expected values in their colours", () => {
  const trace = scenarios["wrong-answer"].submission.artifacts.find((a) => a.kind === "fst");
  if (!trace?.waveform) throw new Error("no trace");
  const items = signalItems(trace.waveform, FIFO.interface.ports, (port) => `${port} ожидалось`);
  expect(items.slice(0, 7)).toEqual([
    { path: "tb_top.clk", color: "Clock", label: "clk" },
    { path: "tb_top.rst_n", color: undefined, label: "rst_n" },
    { path: "tb_top.push", color: undefined, label: "push" },
    { path: "tb_top.wdata", color: "Bus", label: "wdata" },
    { path: "tb_top.pop", color: undefined, label: "pop" },
    { path: "tb_top.rdata", color: "Bus", label: "rdata" },
    { path: "tb_top.exp_rdata", color: "Expected", label: "rdata ожидалось" },
  ]);
});
