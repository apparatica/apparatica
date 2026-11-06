import { expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";

import { references } from "./leaderboards";
import { configureMocks } from "./submissions";
import { mockSession } from "./users";

const client = createApiClient({ baseUrl: "http://localhost" });
const ada = { Cookie: `ap_session=${mockSession("ada")}` };

function leaderboard(slug: string, query: Record<string, unknown> = {}, headers = {}) {
  return client.GET("/api/v1/problems/{slug}/leaderboard", {
    params: { path: { slug }, query },
    headers,
  });
}

it("ranks by the formula: equal metrics share a place, duplicates fold under the earliest", async () => {
  const { data } = await leaderboard("sync-fifo", { per_page: 100 });
  expect(data?.order.map((key) => key.metric)).toEqual([
    "synth.critical_path_ns",
    "synth.area_um2",
  ]);
  const ranks = data?.items.map((row) => row.rank) ?? [];
  expect(ranks[0]).toBe(1);
  const shared = ranks.findIndex((rank, index) => rank === ranks[index + 1]);
  expect(shared).toBeGreaterThanOrEqual(0);
  // 1, 2, 2, 4: the place after a shared one skips.
  const after = ranks.findIndex((rank, index) => index > shared && rank !== ranks[shared]);
  expect(ranks[after]).toBe((ranks[shared] ?? 0) + (after - shared));

  const group = data?.items.find((row) => row.duplicates > 0);
  expect(group?.group.length).toBe(Math.min(group?.duplicates ?? 0, 50));
  expect(data?.total).toBeLessThan(data?.entries ?? 0);

  const flat = await leaderboard("sync-fifo", { group: false, per_page: 100 });
  expect(flat.data?.total).toBe(data?.entries);
  const follower = flat.data?.items.find((row) => row.duplicate_of !== null);
  expect(follower?.rank).toBe(
    flat.data?.items.find((row) => row.solution_id === follower?.duplicate_of?.solution_id)?.rank,
  );
});

it("sorts by a column without changing the places and rejects other sorts", async () => {
  const { data } = await leaderboard("mux4", { sort: "-synth.cells", per_page: 100 });
  const cells = data?.items.map((row) => row.metrics["synth.cells"] ?? 0) ?? [];
  expect(cells).toEqual([...cells].sort((a, b) => b - a));
  const bad = await leaderboard("mux4", { sort: "synth.latches" });
  expect(bad.error?.code).toBe("VALIDATION_ERROR");
});

it("finds the entry of the signed-in user and its page", async () => {
  const { data } = await leaderboard("mux4", { around: "me", per_page: 10 }, ada);
  expect(data?.me?.author.nick).toBe("ada");
  expect(data?.items.some((row) => row.is_me)).toBe(true);
  const guest = await leaderboard("mux4");
  expect(guest.data?.me).toBeNull();

  const profile = await client.GET("/api/v1/users/{nick}", { params: { path: { nick: "ada" } } });
  expect(profile.data?.best_places.map((place) => place.problem.slug).sort()).toEqual([
    "carry-adder",
    "mux4",
  ]);
  expect(profile.data?.rating?.points).toBeGreaterThan(0);
  expect(profile.data?.solutions).toBe(2);

  const global = await client.GET("/api/v1/leaderboard", {
    params: { query: { per_page: 5 } },
    headers: ada,
  });
  expect(global.data?.me?.user.nick).toBe("ada");
  expect(global.data?.around_me.some((row) => row.is_me)).toBe(true);
  expect(global.data?.items.map((row) => row.rank)).toEqual([1, 2, 3, 4, 5]);
});

it("closes the code of others and the reference until an accepted Submit", async () => {
  const listed = await client.GET("/api/v1/problems/{slug}/solutions", {
    params: { path: { slug: "sync-fifo" }, query: { sort: "-submitted_at" } },
  });
  expect(listed.data?.code_locked).toBe(true);
  const id = listed.data?.items[0]?.id ?? "";
  const locked = await client.GET("/api/v1/solutions/{id}", { params: { path: { id } } });
  expect(locked.data).toMatchObject({ code: null, code_locked: true });
  expect(locked.data?.stages.at(-1)?.metrics_schema).toBe("synth/v1");
  const reference = await client.GET("/api/v1/problems/{slug}/reference", {
    params: { path: { slug: "sync-fifo" } },
  });
  expect(reference.error?.code).toBe("REFERENCE_LOCKED");

  configureMocks({ speed: Infinity });
  await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "submit", code: "module sync_fifo; endmodule" },
  });
  const open = await client.GET("/api/v1/solutions/{id}", { params: { path: { id } } });
  expect(open.data?.code_locked).toBe(false);
  const opened = await client.GET("/api/v1/problems/{slug}/reference", {
    params: { path: { slug: "sync-fifo" } },
  });
  expect(opened.data?.solutions[0]?.metrics?.["synth.critical_path_ns"]).toBe(0.91);
});

it("places an accepted Submit of a user and groups the reference code under the earliest", async () => {
  configureMocks({ speed: Infinity });
  const code = references["sync-fifo"]?.[0]?.code ?? "";
  const { data } = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "submit", code },
    headers: ada,
  });
  const id = data?.id ?? "";
  const done = await client.GET("/api/v1/submissions/{id}", {
    params: { path: { id } },
    headers: ada,
  });
  expect(done.data?.public).toBe(true);
  expect(done.data?.leaderboard).toMatchObject({ is_best: true, total: 305 });
  expect(done.data?.leaderboard?.duplicate_of).not.toBeNull();

  const solution = await client.GET("/api/v1/solutions/{id}", { params: { path: { id } } });
  expect(solution.data?.duplicate_of?.solution_id).toBe(done.data?.leaderboard?.duplicate_of);
  expect(solution.data?.metrics["synth.area_um2"]).toBe(902);

  const guest = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "submit", code },
  });
  const guestDone = await client.GET("/api/v1/submissions/{id}", {
    params: { path: { id: guest.data?.id ?? "" } },
  });
  expect(guestDone.data).toMatchObject({ public: false, leaderboard: null });
});
