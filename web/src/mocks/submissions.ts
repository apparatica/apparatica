// Submissions of the mock API. A check replays a recorded scenario (scenarios.ts) in real time from
// its creation: a reload or a reconnect finds it where the real check would be. The scenario is
// picked by a `mock: <name>` mark in the code, e.g. `// mock: wrong-answer` (docs/frontend.md).
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api, problem } from "./http";
import {
  isScenarioName,
  type Scenario,
  type ScenarioName,
  scenarios,
  type StreamEvent,
} from "./scenarios";

type Submission = Schemas["Submission"];
type SubmissionCreate = Schemas["SubmissionCreate"];

/** Presigned URLs of artifacts point here. */
export const STORAGE = "https://storage.mock/artifacts";
const MARK = /\bmock:\s*([\w-]+)/;
const DEFAULT_SCENARIO: Record<SubmissionCreate["kind"], ScenarioName> = {
  run: "run-passed",
  submit: "accepted",
};
const WAVEFORM_MS = 2000; // a recreated FST is ready after this long
const HOUR_MS = 3_600_000;
const NO_VERDICT: Schemas["VerdictDetail"] = {
  first_failure: null,
  limit: null,
  warnings: [],
  error_codes: [],
};

interface Check {
  id: string;
  scenario: Scenario;
  request: SubmissionCreate;
  created: number;
  cancelled?: number;
  waveform?: number;
}

const options = { speed: 1 };
const checks = new Map<string, Check>();

/** `speed: Infinity` finishes every check at once (unit tests). */
export function configureMocks(update: Partial<typeof options>): void {
  Object.assign(options, update);
}

export function resetMocks(): void {
  checks.clear();
  options.speed = 1;
}

const msOf = (id: string) => Number(id.split("-")[0]);

function compareIds(a: string, b: string): number {
  const [aMs = 0, aSeq = 0] = a.split("-").map(Number);
  const [bMs = 0, bSeq = 0] = b.split("-").map(Number);
  return aMs - bMs || aSeq - bSeq;
}

/** When the event of the check is due, in `Date.now()` time. */
function due(check: Check, event: StreamEvent): number {
  const [first] = check.scenario.events;
  return check.created + (msOf(event.id) - msOf(first?.id ?? event.id)) / options.speed;
}

function happened(check: Check, now: number): StreamEvent[] {
  const until = check.cancelled ?? now;
  return check.scenario.events.filter((event) => due(check, event) <= until);
}

/** The submission now: queued, running, finished or cancelled. */
function submissionOf(check: Check, now = Date.now()): Submission {
  const { scenario } = check;
  const final = scenario.submission;
  const shift = check.created - Date.parse(final.created_at); // recorded times -> this check
  const at = (time: string | null) =>
    time === null ? null : new Date(Date.parse(time) + shift).toISOString();
  const seen = happened(check, now);
  const ended = new Set(
    seen.flatMap(({ event }) => (event.type === "stage_end" ? [event.result.key] : [])),
  );
  const stages = final.stages
    .filter((stage) => ended.has(stage.key))
    .map((stage) => ({
      ...stage,
      started_at: at(stage.started_at),
      finished_at: at(stage.finished_at),
    }));
  const common = {
    ...final,
    id: check.id,
    problem: check.request.problem,
    version: check.request.version,
    code: check.request.code,
    created_at: new Date(check.created).toISOString(),
    started_at: at(final.started_at),
  };
  if (check.cancelled !== undefined) {
    return {
      ...common,
      status: "cancelled",
      verdict_detail: NO_VERDICT,
      finished_at: new Date(check.cancelled).toISOString(),
      stages,
      artifacts: [],
    };
  }
  if (seen.some(({ event }) => event.type === "finalized")) {
    return {
      ...common,
      finished_at: at(final.finished_at),
      stages: final.stages.map((stage) => ({
        ...stage,
        started_at: at(stage.started_at),
        finished_at: at(stage.finished_at),
      })),
      artifacts: final.artifacts.map((artifact) =>
        artifact.kind === "fst" &&
        check.waveform !== undefined &&
        now - check.waveform < WAVEFORM_MS / options.speed
          ? { ...artifact, state: "pending", size_bytes: null }
          : artifact,
      ),
    };
  }
  const started = seen.some(({ event }) => event.type === "stage_start");
  const queue = seen.findLast(({ event }) => event.type === "queue")?.event;
  return {
    ...common,
    status: started ? "running" : "queued",
    verdict_detail: null,
    queue_position: !started && queue?.type === "queue" ? queue.position : null,
    eta_s: !started && queue?.type === "queue" ? (queue.eta_s ?? null) : null,
    started_at: started ? common.started_at : null,
    finished_at: null,
    stages,
    artifacts: [],
  };
}

function summaryOf(submission: Submission): Schemas["SubmissionSummary"] {
  const { id, problem_title, version, kind, status, verdict_detail, created_at, finished_at } =
    submission;
  return {
    id,
    problem: submission.problem,
    problem_title,
    version,
    kind,
    status,
    verdict_detail,
    created_at,
    finished_at,
  };
}

function quotaWindow(limit: number, used: number[]): Schemas["QuotaWindow"] {
  const now = Date.now();
  const recent = used.filter((time) => now - time < HOUR_MS).sort((a, b) => a - b);
  const remaining = Math.max(0, limit - recent.length);
  const [oldest] = recent;
  return {
    limit,
    remaining,
    reset_at:
      remaining > 0 || oldest === undefined ? null : new Date(oldest + HOUR_MS).toISOString(),
  };
}

/** The guest quotas of the config fixture, spent by the checks of the mock. */
function quota(): Schemas["QuotaStatus"] {
  const { guest } = fixtures.config.limits.quotas;
  const all = [...checks.values()];
  return {
    checks: quotaWindow(
      guest.checks_per_hour,
      all.map((check) => check.created),
    ),
    waveforms: quotaWindow(
      guest.waveforms_per_hour,
      all.flatMap((check) => (check.waveform === undefined ? [] : [check.waveform])),
    ),
  };
}

/** As the API sends it: a `queue` event is not stored in the stream, so it has no `id:`. */
function format({ id, event }: StreamEvent): string {
  const head = event.type === "queue" ? "" : `id: ${id}\n`;
  return `${head}event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
}

/** The events after `after`, each when it is due; ends after `finalized`. */
function eventStream(
  check: Check,
  after: string | null,
  dropAfter?: number,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const pending = check.scenario.events.filter(
    (event) => after === null || compareIds(event.id, after) > 0,
  );
  let timer: ReturnType<typeof setTimeout> | undefined;
  let last = after ?? "0-0";
  let sent = 0;
  return new ReadableStream({
    start(controller) {
      const send = (event: StreamEvent) => {
        controller.enqueue(encoder.encode(format(event)));
        last = event.id;
        sent += 1;
      };
      // After a cancellation the events due before it still go out, then `finalized`.
      const cut = (event: StreamEvent | undefined) =>
        check.cancelled !== undefined &&
        (event === undefined || due(check, event) > check.cancelled);
      const next = () => {
        const event = pending[0];
        if (cut(event)) {
          const finalized: StreamEvent["event"] = {
            type: "finalized",
            status: "cancelled",
            verdict_detail: NO_VERDICT,
          };
          send({ id: `${msOf(last) + 1}-0`, event: finalized });
          controller.close();
          return;
        }
        if (event === undefined) {
          controller.close();
          return;
        }
        timer = setTimeout(
          () => {
            if (cut(event)) {
              next();
              return;
            }
            pending.shift();
            send(event);
            if (dropAfter !== undefined && sent >= dropAfter) {
              controller.close(); // the stream ends without `finalized`: the client reconnects
            } else if (event.event.type === "finalized") {
              controller.close();
            } else {
              next();
            }
          },
          Math.max(0, due(check, event) - Date.now()),
        );
      };
      next();
    },
    cancel() {
      clearTimeout(timer);
    },
  });
}

function scenarioFor(request: SubmissionCreate): Scenario {
  const name = MARK.exec(request.code)?.[1];
  return scenarios[
    name !== undefined && isScenarioName(name) ? name : DEFAULT_SCENARIO[request.kind]
  ];
}

function notFound(id: string) {
  return problem(404, "NOT_FOUND", `No submission ${id}`);
}

/** `GET /submissions/{id}/events`; `dropAfter` ends the stream after that many events, before
 * `finalized`: a dropped connection for the client. */
export function eventsHandler(settings: { dropAfter?: number } = {}) {
  return http.get(api("/api/v1/submissions/:id/events"), ({ params, request }) => {
    const check = checks.get(String(params.id));
    if (check === undefined) return notFound(String(params.id));
    const after =
      request.headers.get("Last-Event-ID") ?? new URL(request.url).searchParams.get("from");
    return new HttpResponse(eventStream(check, after, settings.dropAfter), {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "private, no-store",
        "X-Accel-Buffering": "no",
      },
    });
  });
}

export const submissionHandlers = [
  http.post(api("/api/v1/submissions"), async ({ request }) => {
    const body = (await request.json()) as SubmissionCreate;
    const left = quota().checks;
    if (left.remaining === 0) {
      const retry = Math.ceil((Date.parse(left.reset_at ?? "") - Date.now()) / 1000);
      return problem(429, "RATE_LIMITED", `Guest limit is ${left.limit} checks per hour`, {
        quota: "checks",
        limit: left.limit,
        window_s: HOUR_MS / 1000,
        retry_after_s: retry,
      });
    }
    const check: Check = {
      id: crypto.randomUUID(),
      scenario: scenarioFor(body),
      request: body,
      created: Date.now(),
    };
    checks.set(check.id, check);
    const created: Schemas["SubmissionCreated"] = { ...submissionOf(check), quota: quota() };
    return HttpResponse.json(created, {
      status: 202,
      headers: { Location: new URL(`/api/v1/submissions/${check.id}`, request.url).href },
    });
  }),

  http.get(api("/api/v1/submissions"), ({ request }) => {
    const slug = new URL(request.url).searchParams.get("problem");
    const items = [...checks.values()]
      .filter((check) => slug === null || check.request.problem === slug)
      .sort((a, b) => b.created - a.created)
      .map((check) => summaryOf(submissionOf(check)));
    const page: Schemas["SubmissionPage"] = { items, next_cursor: null, quota: quota() };
    return HttpResponse.json(page);
  }),

  http.get(api("/api/v1/submissions/:id"), ({ params }) => {
    const check = checks.get(String(params.id));
    return check === undefined
      ? notFound(String(params.id))
      : HttpResponse.json(submissionOf(check));
  }),

  eventsHandler(),

  http.post(api("/api/v1/submissions/:id/cancel"), ({ params }) => {
    const check = checks.get(String(params.id));
    if (check === undefined) return notFound(String(params.id));
    if (submissionOf(check).finished_at !== null) {
      return problem(409, "SUBMISSION_FINISHED", "The check is over");
    }
    check.cancelled = Date.now();
    return new HttpResponse(null, { status: 202 });
  }),

  http.get(api("/api/v1/submissions/:id/artifacts/:kind"), ({ params, request }) => {
    const check = checks.get(String(params.id));
    if (check === undefined) return notFound(String(params.id));
    const stage = new URL(request.url).searchParams.get("stage");
    const artifact = submissionOf(check).artifacts.find(
      (item) =>
        item.kind === params.kind &&
        (stage === null || item.stage === stage) &&
        item.state === "ready",
    );
    if (artifact === undefined)
      return problem(404, "NOT_FOUND", `No ${String(params.kind)} artifact`);
    const query = artifact.stage === null ? "" : `?stage=${artifact.stage}`;
    return new HttpResponse(null, {
      status: 302,
      headers: { Location: `${STORAGE}/${check.id}/${artifact.kind}${query}` },
    });
  }),

  http.get(`${STORAGE}/:id/:kind`, ({ params, request }) => {
    const check = checks.get(String(params.id));
    if (check === undefined) return new HttpResponse(null, { status: 404 });
    const stage = new URL(request.url).searchParams.get("stage");
    const events = check.scenario.events;
    let body: BodyInit;
    if (params.kind === "fst" && check.scenario.files) {
      body = Uint8Array.from(atob(check.scenario.files.fst), (char) => char.charCodeAt(0));
    } else if (params.kind === "log") {
      body = events
        .flatMap(({ event }) => (event.type === "log" && event.stage === stage ? [event.text] : []))
        .join("");
    } else {
      body = events.map((event) => JSON.stringify(event) + "\n").join("");
    }
    return new HttpResponse(body, {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="${String(params.kind)}"`,
      },
    });
  }),

  http.post(api("/api/v1/submissions/:id/waveform"), ({ params }) => {
    const check = checks.get(String(params.id));
    if (check === undefined) return notFound(String(params.id));
    const trace = check.scenario.submission.artifacts.find((artifact) => artifact.kind === "fst");
    if (trace === undefined || submissionOf(check).finished_at === null) {
      return problem(422, "VALIDATION_ERROR", "The submission has no failed test to trace");
    }
    const waves = quota().waveforms;
    if (waves.remaining === 0) {
      const retry = Math.ceil((Date.parse(waves.reset_at ?? "") - Date.now()) / 1000);
      return problem(429, "RATE_LIMITED", `At most ${waves.limit} waveforms per hour`, {
        quota: "waveforms",
        limit: waves.limit,
        window_s: HOUR_MS / 1000,
        retry_after_s: retry,
      });
    }
    check.waveform = Date.now();
    const pending: Schemas["SubmissionArtifact"] = { ...trace, state: "pending", size_bytes: null };
    return HttpResponse.json(pending, { status: 202 });
  }),
];
