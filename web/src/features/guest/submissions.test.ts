import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import {
  type LocalSubmission,
  markGone,
  MAX_SUBMISSIONS,
  readSubmissions,
  rememberSubmissions,
  SUBMISSIONS_KEY,
  useSubmissionHistory,
} from "./submissions";

afterEach(() => localStorage.clear());

function submission(id: string, minute: number, fields: Partial<LocalSubmission> = {}) {
  return {
    id,
    problem: "mux4",
    version: 1,
    kind: "run",
    status: "wrong_answer",
    verdict_detail: null,
    created_at: `2026-10-29T10:${String(minute).padStart(2, "0")}:00Z`,
    ...fields,
  } satisfies LocalSubmission;
}

it("keeps the submissions newest first, as the server shows them", () => {
  rememberSubmissions([submission("a", 1), submission("b", 3, { status: "queued" })]);
  rememberSubmissions([submission("c", 2, { problem: "sync-fifo" })]);
  expect(readSubmissions().map((item) => item.id)).toEqual(["b", "c", "a"]);
  rememberSubmissions([submission("b", 3, { status: "accepted" })]);
  expect(readSubmissions()[0]?.status).toBe("accepted");
  // An older list does not take the finished status back.
  rememberSubmissions([submission("b", 3, { status: "running" })]);
  expect(readSubmissions()[0]?.status).toBe("accepted");
  expect(JSON.parse(localStorage.getItem(SUBMISSIONS_KEY) ?? "").v).toBe(1);
});

it("a finished submission missing from the complete list of its problem is gone", () => {
  rememberSubmissions([
    submission("a", 1),
    submission("b", 2, { status: "queued" }),
    submission("c", 3, { problem: "sync-fifo" }),
    submission("d", 4),
  ]);
  rememberSubmissions([submission("d", 4)], { problem: "mux4" });
  const gone = Object.fromEntries(readSubmissions().map((item) => [item.id, item.gone ?? false]));
  // `b` may have been created after the list was read; `c` is of another problem.
  expect(gone).toEqual({ a: true, b: false, c: false, d: false });
  // Listed again (another cookie came back): not gone.
  rememberSubmissions([submission("a", 1)]);
  expect(readSubmissions().find((item) => item.id === "a")?.gone).toBeUndefined();
  markGone("c");
  expect(readSubmissions().find((item) => item.id === "c")?.gone).toBe(true);
});

it("forgets the oldest past the limit and ignores what it cannot read", () => {
  rememberSubmissions(
    Array.from({ length: MAX_SUBMISSIONS + 2 }, (_, n) =>
      submission(String(n), 0, { created_at: new Date(Date.UTC(2026, 9, 1, 0, n)).toISOString() }),
    ),
  );
  const items = readSubmissions();
  expect(items).toHaveLength(MAX_SUBMISSIONS);
  expect(items.at(-1)?.id).toBe("2");

  for (const raw of ["{", "null", '{"v":2,"items":[]}', '{"v":1,"items":{}}']) {
    localStorage.setItem(SUBMISSIONS_KEY, raw);
    expect(readSubmissions()).toEqual([]);
  }
  localStorage.setItem(
    SUBMISSIONS_KEY,
    JSON.stringify({ v: 1, items: [submission("a", 1), { id: "b", kind: "lint" }] }),
  );
  expect(readSubmissions().map((item) => item.id)).toEqual(["a"]);
});

it("the hook lists the submissions of the problem and follows other tabs", () => {
  const { result } = renderHook(() => useSubmissionHistory("mux4"));
  expect(result.current).toEqual([]);
  act(() => rememberSubmissions([submission("a", 1), submission("b", 2, { problem: "x" })]));
  expect(result.current?.map((item) => item.id)).toEqual(["a"]);
  act(() => {
    localStorage.setItem(SUBMISSIONS_KEY, JSON.stringify({ v: 1, items: [] }));
    window.dispatchEvent(new StorageEvent("storage", { key: SUBMISSIONS_KEY }));
  });
  expect(result.current).toEqual([]);
});
