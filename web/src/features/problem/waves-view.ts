// The waves tab of the results (FR-WAV-*, sheet CmpC, mock-up BenchWave): which trace the check
// has and what the panel shows for it. The judge records one FST per sim stage, the window around
// the first mismatch of the failed open test (docs/api.md#артефакты-и-волны).
import { type Check, isFinished, type Submission } from "@/features/submission/machine";
import type { SignalItem } from "@/features/waveview/viewer";
import type { Schemas } from "@/lib/api/client";

import { failureOf } from "./pipeline-view";

export type Artifact = Schemas["SubmissionArtifact"];
export type Waveform = Schemas["Waveform"];

export interface Trace {
  submission: string;
  stage: string;
  artifact: Artifact;
  waveform: Waveform;
  /** The name of the traced test, its id without one. */
  test: string;
}

/** Why there are no waves. */
export type NoWaves =
  /** The check runs: a trace comes if an open test fails. */
  | "running"
  /** No open test failed. */
  | "noFailure"
  /** A hidden test failed: hidden tests are not traced. */
  | "hidden"
  /** A test failed but its trace was not recorded (e.g. a nondeterministic testbench). */
  | "notRecorded";

export type WavesView =
  | { kind: "none"; reason: NoWaves }
  /** The check is over, its artifacts are being read. */
  | { kind: "waiting" }
  | { kind: "expired"; trace: Trace }
  | { kind: "pending"; trace: Trace }
  /** The recreation failed. */
  | { kind: "failed"; trace: Trace }
  /** The toolchain profile of the check has no viewer: download only. */
  | { kind: "noViewer"; trace: Trace }
  | { kind: "tooBig"; trace: Trace; sizeBytes: number }
  | { kind: "ready"; trace: Trace; viewerUrl: string };

function traceOf(check: Check, submission: Submission): Trace | null {
  const traces = submission.artifacts.filter(
    (artifact): artifact is Artifact & { stage: string; waveform: Waveform } =>
      artifact.kind === "fst" && artifact.stage !== null && artifact.waveform !== null,
  );
  const stage = check.verdict?.first_failure?.stage;
  const artifact = traces.find((item) => item.stage === stage) ?? traces[0];
  if (artifact === undefined) return null;
  const test = check.stages
    .find((item) => item.key === artifact.stage)
    ?.summary.tests.find((item) => item.id === artifact.waveform.test);
  return {
    submission: submission.id,
    stage: artifact.stage,
    artifact,
    waveform: artifact.waveform,
    test: test?.name || artifact.waveform.test,
  };
}

/** `submission` is the stored submission of the check; `maxBytes` the largest FST to view. */
export function wavesView(
  check: Check,
  submission: Submission | null,
  maxBytes: number,
): WavesView {
  if (!isFinished(check)) return { kind: "none", reason: "running" };
  // Read again after `finalized`: until then it has no artifacts.
  if (submission?.id !== check.id || submission.finished_at === null) return { kind: "waiting" };
  const trace = traceOf(check, submission);
  if (trace === null) {
    const failure = failureOf(check);
    const reason =
      failure.kind === "test" ? "notRecorded" : failure.kind === "hidden" ? "hidden" : "noFailure";
    return { kind: "none", reason };
  }
  switch (trace.artifact.state) {
    case "expired":
      return { kind: "expired", trace };
    case "pending":
      return { kind: "pending", trace };
    case "failed":
      return { kind: "failed", trace };
    case "ready":
      break;
  }
  if (submission.waveview_url === null) return { kind: "noViewer", trace };
  const size = trace.artifact.size_bytes ?? 0;
  if (size > maxBytes) return { kind: "tooBig", trace, sizeBytes: size };
  return { kind: "ready", trace, viewerUrl: submission.waveview_url };
}

/** The test the check traced, by id: "Show on the diagram" goes with its row. */
export function tracedTest(view: WavesView): string | null {
  return "trace" in view ? view.trace.waveform.test : null;
}

export type Ports = Schemas["Interface"]["ports"];

/** The signals in the order of the judge (ADR-0004): the clock, inputs, each output and what the
 * model expected of it. Buses get the bus colour, one-bit lines the colour of the text. */
export function signalItems(
  waveform: Waveform,
  ports: Ports,
  expectedLabel: (port: string) => string,
): SignalItem[] {
  const widths = new Map(ports.map((port) => [port.name, port.width.trim()]));
  return waveform.signals.map(({ path, port, role }) => {
    if (role === "clock") return { path, color: "Clock", label: port };
    if (role === "expected") return { path, color: "Expected", label: expectedLabel(port) };
    const width = widths.get(port);
    return { path, color: width === undefined || width === "1" ? undefined : "Bus", label: port };
  });
}
