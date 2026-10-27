import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { HISTORY_KEY, readHistory, recordCheck, useHistory } from "./history";

afterEach(() => localStorage.clear());

const check = { problem: "mux4", difficulty: "easy" } as const;

it("an accepted Submit solves a problem, any other check tries it", () => {
  recordCheck({ ...check, kind: "run", status: "accepted" });
  expect(readHistory()).toEqual({ mux4: { status: "attempted", difficulty: "easy" } });
  recordCheck({ ...check, kind: "submit", status: "accepted_with_warnings" });
  expect(readHistory().mux4?.status).toBe("solved");
  recordCheck({ ...check, kind: "submit", status: "wrong_answer" });
  expect(readHistory().mux4?.status).toBe("solved"); // stays solved
  recordCheck({ problem: "sync-fifo", difficulty: "medium", kind: "submit", status: "cancelled" });
  expect(readHistory()["sync-fifo"]).toEqual({ status: "attempted", difficulty: "medium" });
  expect(JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "")).toEqual({
    v: 1,
    problems: {
      mux4: { status: "solved", difficulty: "easy" },
      "sync-fifo": { status: "attempted", difficulty: "medium" },
    },
  });
});

it("ignores a history it cannot read", () => {
  for (const raw of ["{", "null", '{"v":2,"problems":{}}', '{"v":1,"problems":7}']) {
    localStorage.setItem(HISTORY_KEY, raw);
    expect(readHistory()).toEqual({});
  }
  localStorage.setItem(
    HISTORY_KEY,
    '{"v":1,"problems":{"mux4":{"status":"solved","difficulty":"easy"},"x":{"status":"?"}}}',
  );
  expect(Object.keys(readHistory())).toEqual(["mux4"]);
});

it("the hook follows the checks of this tab and of other tabs", () => {
  const { result } = renderHook(() => useHistory());
  expect(result.current).toEqual({});
  const first = result.current;
  act(() => recordCheck({ ...check, kind: "submit", status: "accepted" }));
  expect(result.current?.mux4?.status).toBe("solved");
  expect(result.current).not.toBe(first);

  act(() => {
    localStorage.setItem(HISTORY_KEY, '{"v":1,"problems":{}}');
    window.dispatchEvent(new StorageEvent("storage", { key: HISTORY_KEY }));
  });
  expect(result.current).toEqual({});
});
