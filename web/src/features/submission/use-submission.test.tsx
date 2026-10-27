import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { api } from "@/mocks/http";
import { scenarios } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { configureMocks, eventsHandler } from "@/mocks/submissions";
import { Providers } from "@/test/render";

import { useSubmission, type UseSubmissionOptions } from "./use-submission";

const FAST = [5, 5, 5, 5, 5];
const CODE = "module sync_fifo; endmodule";

function setup(options: Partial<UseSubmissionOptions> = {}) {
  return renderHook(
    (props: Partial<UseSubmissionOptions>) =>
      useSubmission({ problem: "sync-fifo", version: 1, reconnectDelaysMs: FAST, ...props }),
    { wrapper: Providers, initialProps: options },
  );
}

type Result = ReturnType<typeof setup>["result"];

async function ready(result: Result) {
  await waitFor(() => expect(result.current.restoring).toBe(false));
}

function linesOf(result: Result): string[] {
  return (result.current.check?.console ?? []).flatMap((entry) =>
    entry.kind === "line" ? [entry.text] : [],
  );
}

const recordedLines = (name: keyof typeof scenarios) =>
  scenarios[name].events.flatMap(({ event }) =>
    event.type === "log" ? event.text.split("\n").slice(0, -1) : [],
  );

it("starts a check, follows it to finalized and reads the stored result", async () => {
  configureMocks({ speed: Infinity });
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  // Holds the request, then falls through to the handler of the mocks.
  server.use(http.post(api("/api/v1/submissions"), () => held));
  const { result } = setup();
  await ready(result);
  expect(result.current.check).toBeNull();

  act(() => result.current.start({ kind: "run", code: `// mock: wrong-answer\n${CODE}` }));
  await waitFor(() => expect(result.current.starting).toBe("run"));
  release();
  await waitFor(() => expect(result.current.check).not.toBeNull());
  expect(result.current.starting).toBeNull();
  expect(result.current.quota?.checks.remaining).toBe(9);

  await waitFor(() => expect(result.current.connection).toEqual({ state: "closed" }));
  const { check } = result.current;
  expect(check?.status).toBe("wrong_answer");
  expect(check?.verdict).toEqual(scenarios["wrong-answer"].submission.verdict_detail);
  expect(linesOf(result)).toEqual(recordedLines("wrong-answer"));
  // After finalized the stored submission is read again: now with the trace.
  await waitFor(() =>
    expect(result.current.submission?.artifacts.map((item) => item.kind)).toContain("fst"),
  );
});

it("shows the queue position the check was created with", async () => {
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "submit", code: CODE }));
  await waitFor(() => expect(result.current.check).not.toBeNull());
  expect(result.current.check).toMatchObject({ status: "queued", queue: { position: 2 } });
  expect(result.current.submission?.status).toBe("queued");
});

it("resumes a dropped stream after the last event without duplicates", async () => {
  configureMocks({ speed: Infinity });
  server.use(eventsHandler({ dropAfter: 4 }));
  const { result } = setup();
  await ready(result);

  act(() => result.current.start({ kind: "submit", code: `// mock: output-limit\n${CODE}` }));
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));
  expect(result.current.check?.status).toBe("limit_exceeded");
  expect(linesOf(result)).toEqual(recordedLines("output-limit"));
  const lost = result.current.check?.console.filter((entry) => entry.kind === "lost") ?? [];
  expect(lost.length).toBeGreaterThan(1);
});

it("gives up after the last delay and connects again on request", async () => {
  configureMocks({ speed: Infinity });
  server.use(http.get(api("/api/v1/submissions/:id/events"), () => HttpResponse.error()));
  const { result } = setup();
  await ready(result);

  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.connection?.state).toBe("failed"));
  const failed = result.current.connection;
  expect(failed).toMatchObject({ state: "failed", error: null });
  // One mark per loss, not per reconnect.
  const marks = result.current.check?.console.filter((entry) => entry.kind === "lost");
  expect(marks).toEqual([{ kind: "lost", at: failed?.state === "failed" ? failed.lostAt : 0 }]);

  server.resetHandlers();
  act(() => result.current.reconnect());
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));
  expect(result.current.check?.status).toBe("accepted");
});

it("waits between reconnects", async () => {
  server.use(http.get(api("/api/v1/submissions/:id/events"), () => HttpResponse.error()));
  const { result } = setup({ reconnectDelaysMs: [60_000] });
  await ready(result);

  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.connection?.state).toBe("waiting"));
  expect(result.current.connection).toMatchObject({ state: "waiting", retry: 1 });
  const waiting = result.current.connection;
  if (waiting?.state === "waiting") expect(waiting.at - waiting.lostAt).toBe(60_000);
});

it("cancels the check", async () => {
  configureMocks({ speed: 20 });
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("running"));

  act(() => result.current.cancel());
  await waitFor(() => expect(result.current.check?.status).toBe("cancelled"));
  expect(result.current.cancelling).toBe(false);
  expect(result.current.error).toBeNull();
  expect(result.current.check?.stages.some((stage) => stage.status === "running")).toBe(false);
  expect(result.current.check?.stages.at(-1)?.status).toBe("cancelled");
});

it("restores the last submission of the problem and replays its console", async () => {
  configureMocks({ speed: Infinity });
  const client = createApiClient({ baseUrl: "http://localhost" });
  for (const mark of ["compile-error", "wrong-answer"]) {
    await client.POST("/api/v1/submissions", {
      body: { problem: "sync-fifo", version: 1, kind: "run", code: `// mock: ${mark}` },
    });
  }
  const { result } = setup();
  expect(result.current.restoring).toBe(true);
  await waitFor(() => expect(result.current.check?.status).toBe("wrong_answer"));
  expect(result.current.quota?.checks.remaining).toBe(8);
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));
  expect(linesOf(result)).toEqual(recordedLines("wrong-answer"));
  expect(result.current.submission?.id).toBe(result.current.check?.id);
});

it("reads the stream of a restored check that is still running", async () => {
  configureMocks({ speed: 10 });
  const client = createApiClient({ baseUrl: "http://localhost" });
  const created = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "run", code: "// mock: retry" },
  });
  const { result } = setup();
  await waitFor(() => expect(result.current.check?.id).toBe(created.data?.id));
  expect(result.current.check?.status).not.toBe("accepted");
  await waitFor(() => expect(result.current.check?.status).toBe("accepted"), { timeout: 5000 });
  expect(result.current.check?.attempt).toBe(2);
});

it("drops the previous check when a new one starts", async () => {
  configureMocks({ speed: 5 });
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("running"));
  const first = result.current.check?.id;

  configureMocks({ speed: Infinity });
  act(() => result.current.start({ kind: "run", code: `// mock: compile-error\n${CODE}` }));
  await waitFor(() => expect(result.current.check?.id).not.toBe(first));
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));
  expect(result.current.check?.status).toBe("compile_error");
  expect(linesOf(result)).toEqual(recordedLines("compile-error"));
});

it("keeps the check when the API refuses a new one", async () => {
  configureMocks({ speed: Infinity });
  const { result } = setup();
  await ready(result);
  for (let i = 0; i < 10; i++) {
    act(() => result.current.start({ kind: "run", code: CODE }));
    await waitFor(() => expect(result.current.quota?.checks.remaining).toBe(9 - i));
  }
  const last = result.current.check?.id;

  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.error).not.toBeNull());
  expect(result.current.error).toMatchObject({ code: "RATE_LIMITED", params: { quota: "checks" } });
  expect(result.current.check?.id).toBe(last);
});

it("stops when the submission is gone", async () => {
  configureMocks({ speed: Infinity });
  server.use(
    http.get(api("/api/v1/submissions/:id/events"), () =>
      HttpResponse.json(
        { type: "about:blank", title: "Not Found", status: 404, code: "NOT_FOUND" },
        { status: 404, headers: { "Content-Type": "application/problem+json" } },
      ),
    ),
  );
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.connection?.state).toBe("failed"));
  expect(result.current.connection).toMatchObject({ error: { code: "NOT_FOUND" } });
});

it("shows only the checks of the open problem", async () => {
  configureMocks({ speed: Infinity });
  const { result, rerender } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));

  rerender({ problem: "mux4" });
  expect(result.current.check).toBeNull();
  expect(result.current.connection).toBeNull();
  await ready(result);
  expect(result.current.check).toBeNull();
});
