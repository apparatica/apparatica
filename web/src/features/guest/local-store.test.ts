import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";

import { readHistory, recordCheck, useHistory } from "./history";
import { setStoreOwner } from "./local-store";
import { readSubmissions, rememberSubmissions } from "./submissions";

const check = { problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" } as const;
const submission = {
  id: "s1",
  problem: "mux4",
  version: 2,
  kind: "run",
  status: "accepted",
  verdict_detail: null,
  created_at: "2026-11-04T10:00:00Z",
} as const;

it("keeps a signed-in user's values in memory and the guest's in storage", () => {
  recordCheck({ ...check, problem: "carry-adder" });
  const guestHistory = localStorage.getItem("ap_history");
  const { result } = renderHook(() => useHistory());
  expect(Object.keys(result.current ?? {})).toEqual(["carry-adder"]);

  act(() => setStoreOwner("user"));
  expect(result.current).toEqual({}); // the guest's are not shown
  act(() => {
    recordCheck(check);
    rememberSubmissions([submission]);
  });
  expect(result.current).toEqual({ mux4: { status: "solved", difficulty: "easy" } });
  expect(readSubmissions().map((item) => item.id)).toEqual(["s1"]);
  expect(localStorage.getItem("ap_history")).toBe(guestHistory);
  expect(localStorage.getItem("ap_submissions")).toBeNull();

  act(() => setStoreOwner("guest"));
  expect(Object.keys(result.current ?? {})).toEqual(["carry-adder"]);
  expect(readSubmissions()).toEqual([]);
  act(() => setStoreOwner("user"));
  expect(readHistory()).toEqual({}); // a new owner starts empty
});
