// The state of a check as the results panel shows it, folded from the events of
// GET /submissions/{id}/events (docs/api.md#события-проверки). The final status comes only with
// `finalized`; a worker event with a new attempt number starts the results over.
import type { Schemas } from "@/lib/api/client";

export type Submission = Schemas["Submission"];
export type SubmissionEvent = Schemas["SubmissionEvent"];
export type Status = Submission["status"];
export type Stage = Schemas["StageResult"];
export type Heartbeat = Schemas["HeartbeatEvent"];

/** A row of the console: a line of a stage, the output limit, or a lost connection. */
export type ConsoleEntry =
  | { kind: "line"; stage: string; ch: Schemas["LogEvent"]["ch"]; text: string }
  | { kind: "truncated"; stage: string; limitKb: number }
  | { kind: "lost"; at: number };

export interface Check {
  id: string;
  problem: string;
  kind: Submission["kind"];
  /** queued, running, then the status of `finalized` (or of the stored submission). */
  status: Status;
  queue: { position: number; etaS: number | null } | null;
  /** The attempt the results belong to; 0 before the first worker event. */
  attempt: number;
  /** In pipeline order; a started stage is `running` until its `stage_end`. */
  stages: Stage[];
  /** The last heartbeat of the running stage. */
  heartbeat: Heartbeat | null;
  /** When the running stage began, in `Date.now()` time of the browser: set by `stage_start`,
   * moved by each heartbeat to its elapsed time. */
  runningSince: number | null;
  console: ConsoleEntry[];
  /** The worker finished the pipeline; the verdict waits for `finalized`. */
  done: boolean;
  verdict: Schemas["VerdictDetail"] | null;
  /** The id of the last event applied: the stream resumes after it. */
  lastEventId: string | null;
}

/** Compares the ids of stream entries, `<ms>-<seq>`. */
export function compareEventIds(a: string, b: string): number {
  const [aMs = 0, aSeq = 0] = a.split("-").map(Number);
  const [bMs = 0, bSeq = 0] = b.split("-").map(Number);
  return aMs - bMs || aSeq - bSeq;
}

function stageOf(stage: Submission["stages"][number]): Stage {
  const { key, type, ordinal, status, failure_kind, error_code, started_at, duration_ms } = stage;
  const { metrics_schema, metrics, summary } = stage;
  return {
    key,
    type,
    ordinal,
    status,
    failure_kind,
    limit: null,
    error_code,
    started_at,
    duration_ms,
    metrics_schema,
    metrics,
    cached: false,
    summary,
  };
}

/** The check as `GET` or `POST /submissions` returned it; the events then replay over it. */
export function checkOf(submission: Submission): Check {
  const finished = submission.finished_at !== null;
  return {
    id: submission.id,
    problem: submission.problem,
    kind: submission.kind,
    status: submission.status,
    queue:
      submission.queue_position === null
        ? null
        : { position: submission.queue_position, etaS: submission.eta_s },
    attempt: 0,
    stages: submission.stages.map(stageOf),
    heartbeat: null,
    runningSince: null,
    console: [],
    done: finished,
    verdict: submission.verdict_detail,
    lastEventId: null,
  };
}

function putStage(stages: Stage[], stage: Stage): Stage[] {
  return [...stages.filter((item) => item.key !== stage.key), stage].sort(
    (a, b) => a.ordinal - b.ordinal,
  );
}

function linesOf(event: Schemas["LogEvent"]): ConsoleEntry[] {
  const lines = event.text.split("\n");
  if (lines.at(-1) === "") lines.pop();
  return lines.map((text) => ({ kind: "line", stage: event.stage, ch: event.ch, text }));
}

/** The check after one event of its stream; `id` is the SSE id (null for `queue`), `now` is when
 * the event came. */
export function applyEvent(
  check: Check,
  id: string | null,
  event: SubmissionEvent,
  now: number = Date.now(),
): Check {
  if (id !== null && check.lastEventId !== null && compareEventIds(id, check.lastEventId) <= 0) {
    return check; // already applied: a replay after a reconnect
  }
  let next: Check = { ...check, lastEventId: id ?? check.lastEventId };
  if ("attempt" in event && event.attempt > next.attempt) {
    // A new attempt (or the first event of a restored check): the results start over.
    next = {
      ...next,
      attempt: event.attempt,
      stages: [],
      heartbeat: null,
      runningSince: null,
      console: [],
      done: false,
    };
  } else if ("attempt" in event && event.attempt < next.attempt) {
    return next;
  }
  switch (event.type) {
    case "queue":
      if (next.status !== "queued") return check;
      return { ...next, queue: { position: event.position, etaS: event.eta_s } };
    case "stage_start":
      return {
        ...next,
        status: next.status === "queued" ? "running" : next.status,
        queue: null,
        heartbeat: null,
        runningSince: now,
        stages: putStage(next.stages, {
          key: event.stage,
          type: event.stage_type,
          ordinal: event.ordinal,
          status: "running",
          failure_kind: null,
          limit: null,
          error_code: null,
          started_at: null,
          duration_ms: null,
          metrics_schema: null,
          metrics: {},
          cached: false,
          summary: { diagnostics: [], tests: [] },
        }),
      };
    case "log":
      return { ...next, console: [...next.console, ...linesOf(event)] };
    case "heartbeat":
      return { ...next, heartbeat: event, runningSince: now - event.elapsed_ms };
    case "test":
      return {
        ...next,
        stages: next.stages.map((stage) => {
          if (stage.key !== event.stage) return stage;
          const tests = stage.summary.tests;
          const at = tests.findIndex((test) => test.id === event.test.id);
          return {
            ...stage,
            summary: {
              ...stage.summary,
              tests: at === -1 ? [...tests, event.test] : tests.with(at, event.test),
            },
          };
        }),
      };
    case "truncated":
      return {
        ...next,
        console: [
          ...next.console,
          { kind: "truncated", stage: event.stage, limitKb: event.limit_kb },
        ],
      };
    case "stage_end":
      return {
        ...next,
        heartbeat: next.heartbeat?.stage === event.result.key ? null : next.heartbeat,
        runningSince: null,
        stages: putStage(next.stages, event.result),
      };
    case "done":
      return { ...next, done: true };
    case "finalized":
      // A check cancelled or lost before its stage ended leaves the stage running.
      return {
        ...next,
        status: event.status,
        verdict: event.verdict_detail,
        queue: null,
        heartbeat: null,
        runningSince: null,
        done: true,
        stages: next.stages.map((stage) =>
          stage.status === "running"
            ? { ...stage, status: event.status === "cancelled" ? "cancelled" : "error" }
            : stage,
        ),
      };
  }
}

/** A connection lost at `at`: a mark in the console. */
export function markLost(check: Check, at: number): Check {
  return { ...check, console: [...check.console, { kind: "lost", at }] };
}

export function isFinished(check: Check): boolean {
  return check.status !== "queued" && check.status !== "running";
}
