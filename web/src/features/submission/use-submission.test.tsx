import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { readHistory } from "@/features/guest/history";
import { readSubmissions, rememberSubmissions } from "@/features/guest/submissions";
import { createApiClient } from "@/lib/api/client";
import { api } from "@/mocks/http";
import { scenarios } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { configureMocks, eventsHandler } from "@/mocks/submissions";
import { Providers } from "@/test/render";

import { onFinished } from "./finished";
import { useSubmission, type UseSubmissionOptions } from "./use-submission";

const FAST = [5, 5, 5, 5, 5];
const CODE = "module sync_fifo; endmodule";

function setup(options: Partial<UseSubmissionOptions> = {}) {
  return renderHook(
    (props: Partial<UseSubmissionOptions>) =>
      useSubmission({
        problem: "sync-fifo",
        version: 1,
        title: "Синхронный FIFO",
        difficulty: "medium",
        reconnectDelaysMs: FAST,
        ...props,
      }),
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
  expect(readHistory()["sync-fifo"]).toEqual({ status: "attempted", difficulty: "medium" });
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
  // A reconnect every 4 events: more than the 1 s of waitFor on a loaded machine.
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"), {
    timeout: 5000,
  });
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
  expect(result.current.connection).toMatchObject({ state: "waiting", retry: 1, retries: 1 });
  const waiting = result.current.connection;
  if (waiting?.state === "waiting") expect(waiting.at - waiting.lostAt).toBe(60_000);
});

it("cancels the check", async () => {
  configureMocks({ speed: 20 });
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("running"));

  expect(result.current.cancelRequested).toBe(false);
  act(() => result.current.cancel());
  await waitFor(() => expect(result.current.check?.status).toBe("cancelled"));
  expect(result.current.cancelRequested).toBe(true);
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
  expect(readHistory()["sync-fifo"]?.status).toBe("attempted");
});

it("follows a newer submission of the problem on request", async () => {
  configureMocks({ speed: Infinity });
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.connection?.state).toBe("closed"));
  const shown = result.current.check?.id;
  await expect(act(() => result.current.showLatest())).resolves.toBe(false);
  expect(result.current.check?.id).toBe(shown);

  // Another tab checks the problem.
  const client = createApiClient({ baseUrl: "http://localhost" });
  const created = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "submit", code: CODE },
  });
  await expect(act(() => result.current.showLatest())).resolves.toBe(true);
  expect(result.current.check?.id).toBe(created.data?.id);
  await waitFor(() => expect(result.current.check?.status).toBe("accepted"));
});

it("keeps the submissions of the problem in the local history", async () => {
  configureMocks({ speed: Infinity });
  // Deleted by the server when its time ran out.
  rememberSubmissions([
    {
      id: "00000000-0000-4000-8000-000000000001",
      problem: "sync-fifo",
      version: 1,
      kind: "run",
      status: "accepted",
      verdict_detail: null,
      created_at: "2026-10-01T10:00:00Z",
    },
  ]);
  const client = createApiClient({ baseUrl: "http://localhost" });
  const other = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "submit", code: CODE },
  });
  const { result } = setup();
  await ready(result);
  expect(result.current.check?.id).toBe(other.data?.id);
  act(() =>
    result.current.start({
      kind: "run",
      code: `// mock: wrong-answer
${CODE}`,
    }),
  );
  await waitFor(() => expect(result.current.submission?.status).toBe("wrong_answer"));
  await waitFor(() => expect(readSubmissions()[0]?.status).toBe("wrong_answer"));
  const items = readSubmissions();
  expect(items.map((item) => [item.kind, item.status, item.gone ?? false])).toEqual([
    ["run", "wrong_answer", false],
    ["submit", "accepted", false],
    ["run", "accepted", true],
  ]);
  expect(items[0]?.verdict_detail?.first_failure?.test_number).toBe(2);
});

it("opens the wanted submission, the last one when it is gone, and one from the list", async () => {
  configureMocks({ speed: Infinity });
  const client = createApiClient({ baseUrl: "http://localhost" });
  const body = { problem: "sync-fifo", version: 1, code: CODE } as const;
  const first = await client.POST("/api/v1/submissions", { body: { ...body, kind: "run" } });
  const last = await client.POST("/api/v1/submissions", { body: { ...body, kind: "submit" } });
  const wanted = first.data?.id;
  const { result } = setup({ wanted });
  await ready(result);
  expect(result.current.check?.id).toBe(wanted);

  const missing = "00000000-0000-4000-8000-000000000002";
  rememberSubmissions([{ ...(first.data as NonNullable<typeof first.data>), id: missing }]);
  const reopened = setup({ wanted: missing });
  await ready(reopened.result);
  expect(reopened.result.current.check?.id).toBe(last.data?.id);
  expect(readSubmissions().find((item) => item.id === missing)?.gone).toBe(true);

  act(() => reopened.result.current.show(first.data as NonNullable<typeof first.data>));
  expect(reopened.result.current.check?.id).toBe(wanted);
});

it("an accepted Submit solves the problem in the local history", async () => {
  configureMocks({ speed: Infinity });
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "submit", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("accepted"));
  await waitFor(() =>
    expect(readHistory()["sync-fifo"]).toEqual({ status: "solved", difficulty: "medium" }),
  );
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
  let reread = false;
  server.use(
    http.get(api("/api/v1/submissions"), ({ request }) => {
      if (new URL(request.url).searchParams.get("limit") === "1") reread = true;
      return undefined; // falls through to the handler of the mocks
    }),
  );

  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.error).not.toBeNull());
  expect(result.current.error).toMatchObject({ code: "RATE_LIMITED", params: { quota: "checks" } });
  expect(result.current.failedAt).toEqual(expect.any(Number));
  expect(result.current.check?.id).toBe(last);
  // The spent quota is read again: it may have been spent in another tab.
  await waitFor(() => expect(reread).toBe(true));
  expect(result.current.quota?.checks.remaining).toBe(0);
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

it("goes on in the background after the page closes and tells how it ended", async () => {
  configureMocks({ speed: 10 });
  const finished = vi.fn();
  const unsubscribe = onFinished(finished);
  const { result, unmount } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "submit", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("running"));
  const id = result.current.check?.id;

  unmount();
  await waitFor(() => expect(finished).toHaveBeenCalledOnce(), { timeout: 5000 });
  expect(finished).toHaveBeenCalledWith(
    { id, problem: "sync-fifo", title: "Синхронный FIFO", kind: "submit", status: "accepted" },
    true,
  );
  expect(readHistory()["sync-fifo"]).toEqual({ status: "solved", difficulty: "medium" });
  await waitFor(() =>
    expect(readSubmissions().find((item) => item.id === id)?.status).toBe("accepted"),
  );
  unsubscribe();
});

it("takes its check back from the background when the page opens again", async () => {
  configureMocks({ speed: 10 });
  const finished = vi.fn();
  const unsubscribe = onFinished(finished);
  const first = setup();
  await ready(first.result);
  act(() => first.result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(first.result.current.check?.status).toBe("running"));
  first.unmount();

  const { result } = setup();
  await waitFor(() => expect(result.current.check?.status).toBe("accepted"), { timeout: 5000 });
  expect(finished).not.toHaveBeenCalled();
  unsubscribe();
});

it("tells about a check that ends in a hidden tab", async () => {
  configureMocks({ speed: 10 });
  const finished = vi.fn();
  const unsubscribe = onFinished(finished);
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  const { result } = setup();
  await ready(result);
  act(() =>
    result.current.start({
      kind: "run",
      code: `// mock: wrong-answer
${CODE}`,
    }),
  );
  await waitFor(() => expect(finished).toHaveBeenCalledOnce(), { timeout: 5000 });
  expect(finished).toHaveBeenCalledWith(
    expect.objectContaining({ kind: "run", status: "wrong_answer" }),
    false,
  );
  visibility.mockRestore();
  unsubscribe();
});

it("does not tell about a check the page shows", async () => {
  configureMocks({ speed: Infinity });
  const finished = vi.fn();
  const unsubscribe = onFinished(finished);
  const { result } = setup();
  await ready(result);
  act(() => result.current.start({ kind: "run", code: CODE }));
  await waitFor(() => expect(result.current.check?.status).toBe("accepted"));
  expect(finished).not.toHaveBeenCalled();
  unsubscribe();
});
