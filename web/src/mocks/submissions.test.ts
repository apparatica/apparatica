import { expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";

import { scenarios } from "./scenarios";
import { server } from "./server";
import { configureMocks, eventsHandler } from "./submissions";

const BASE = "http://localhost";
const client = createApiClient({ baseUrl: BASE });

async function submit(code: string, kind: "run" | "submit" = "run") {
  return client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind, code },
  });
}

function events(path: string, headers: Record<string, string> = {}) {
  return fetch(`${BASE}${path}`, { headers: { Accept: "text/event-stream", ...headers } });
}

/** SSE frames of a body: `id`, `event` and the parsed `data`. */
function parse(text: string) {
  return text
    .split("\n\n")
    .filter(Boolean)
    .map((frame) => {
      const fields = Object.fromEntries(
        frame
          .split("\n")
          .map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 2)]),
      );
      return { id: fields.id, event: fields.event, data: JSON.parse(fields.data ?? "null") };
    });
}

it("replays the scenario picked by the mark in the code", async () => {
  const { data, response } = await submit("// mock: wrong-answer\nmodule sync_fifo; endmodule");
  expect(response.status).toBe(202);
  expect(response.headers.get("Location")).toBe(`${BASE}/api/v1/submissions/${data?.id}`);
  expect(data).toMatchObject({
    status: "queued",
    queue_position: 2,
    stages: [],
    verdict_detail: null,
  });
  expect(data?.quota?.checks).toEqual({ limit: 10, remaining: 9, reset_at: null });

  configureMocks({ speed: Infinity });
  const done = await client.GET("/api/v1/submissions/{id}", {
    params: { path: { id: data?.id ?? "" } },
  });
  const recorded = scenarios["wrong-answer"].submission;
  expect(done.data?.status).toBe("wrong_answer");
  expect(done.data?.verdict_detail).toEqual(recorded.verdict_detail);
  expect(done.data?.stages.map((stage) => [stage.key, stage.status])).toEqual(
    recorded.stages.map((stage) => [stage.key, stage.status]),
  );
  expect(done.data?.created_at).toBe(data?.created_at);
  expect(done.data?.code).toContain("mock: wrong-answer");
});

it("streams the events of the check up to finalized and resumes after Last-Event-ID", async () => {
  configureMocks({ speed: Infinity });
  const { data } = await submit("module sync_fifo; endmodule", "submit");
  const recorded = scenarios.accepted.events;
  const path = `/api/v1/submissions/${data?.id}/events`;

  const response = await events(path);
  expect(response.headers.get("Content-Type")).toBe("text/event-stream");
  const frames = parse(await response.text());
  const ids = recorded.map((item) => (item.event.type === "queue" ? undefined : item.id));
  expect(frames.map((frame) => frame.id)).toEqual(ids);
  expect(frames.map((frame) => frame.event)).toEqual(recorded.map((item) => item.event.type));
  expect(frames.at(-1)?.data).toMatchObject({ type: "finalized", status: "accepted" });

  const resumed = parse(
    await (await events(path, { "Last-Event-ID": recorded[4]?.id ?? "" })).text(),
  );
  expect(resumed.map((frame) => frame.id)).toEqual(recorded.slice(5).map((item) => item.id));
});

it("drops the connection when asked", async () => {
  configureMocks({ speed: Infinity });
  server.use(eventsHandler({ dropAfter: 3 }));
  const { data } = await submit("module sync_fifo; endmodule");
  const frames = parse(await (await events(`/api/v1/submissions/${data?.id}/events`)).text());
  expect(frames.map((frame) => frame.event)).toEqual(["queue", "queue", "stage_start"]);
});

it("cancels a running check once", async () => {
  configureMocks({ speed: 20 });
  const { data } = await submit("module sync_fifo; endmodule");
  const id = data?.id ?? "";
  const cancel = await client.POST("/api/v1/submissions/{id}/cancel", { params: { path: { id } } });
  expect(cancel.response.status).toBe(202);

  const frames = parse(await (await events(`/api/v1/submissions/${id}/events`)).text());
  expect(frames.at(-1)?.data).toMatchObject({ type: "finalized", status: "cancelled" });
  const after = await client.GET("/api/v1/submissions/{id}", { params: { path: { id } } });
  expect(after.data?.status).toBe("cancelled");
  const again = await client.POST("/api/v1/submissions/{id}/cancel", { params: { path: { id } } });
  expect(again.error?.code).toBe("SUBMISSION_FINISHED");
});

it("redirects to the artifact files", async () => {
  configureMocks({ speed: Infinity });
  const { data } = await submit("// mock: wrong-answer");
  const id = data?.id ?? "";
  const done = await client.GET("/api/v1/submissions/{id}", { params: { path: { id } } });
  const trace = done.data?.artifacts.find((artifact) => artifact.kind === "fst");
  expect(trace).toMatchObject({ state: "ready", waveform: { scope: "failure_window" } });

  const redirect = await fetch(`${BASE}/api/v1/submissions/${id}/artifacts/fst`, {
    redirect: "manual",
  });
  expect(redirect.status).toBe(302);
  const file = await fetch(redirect.headers.get("Location") ?? "");
  expect((await file.arrayBuffer()).byteLength).toBe(trace?.size_bytes);

  const kept = await client.POST("/api/v1/submissions/{id}/waveform", {
    params: { path: { id } },
    body: { scope: "failure_window", test: null },
  });
  expect(kept.data?.state).toBe("ready"); // as it is: nothing to recreate
});

it("recreates an expired trace", async () => {
  configureMocks({ speed: Infinity });
  const { data } = await submit("// mock: wrong-answer\n// mock-fst: expired");
  const id = data?.id ?? "";
  const trace = async () => {
    const { data } = await client.GET("/api/v1/submissions/{id}", { params: { path: { id } } });
    return data?.artifacts.find((artifact) => artifact.kind === "fst");
  };
  expect(await trace()).toMatchObject({ state: "expired", waveform: { cursor_time_ps: 300 } });
  const missing = await fetch(`${BASE}/api/v1/submissions/${id}/artifacts/fst?stage=sim_run`, {
    redirect: "manual",
  });
  expect(missing.status).toBe(404);

  const request = (scope: "failure_window" | "full_test") =>
    client.POST("/api/v1/submissions/{id}/waveform", {
      params: { path: { id } },
      body: { scope, test: null },
    });
  expect((await request("full_test")).error?.code).toBe("UNAUTHENTICATED");
  const pending = await request("failure_window");
  expect(pending.response.status).toBe(202);
  expect(pending.data?.state).toBe("pending");
  expect((await trace())?.state).toBe("ready"); // at Infinity speed the job is done at once
});

it("limits the checks of a guest", async () => {
  for (let i = 0; i < 10; i++) await submit("module sync_fifo; endmodule");
  const { error, response } = await submit("module sync_fifo; endmodule");
  expect(response.status).toBe(429);
  expect(error?.code).toBe("RATE_LIMITED");
  expect(error?.params?.quota).toBe("checks");
  expect(error?.params?.retry_after_s).toBeGreaterThan(3500);
});

it("does not know other submissions", async () => {
  const { error, response } = await client.GET("/api/v1/submissions/{id}", {
    params: { path: { id: "0192d1a2-7c00-7000-8000-000000000001" } },
  });
  expect(response.status).toBe(404);
  expect(error?.code).toBe("NOT_FOUND");
});
