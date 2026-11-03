import { expect, it } from "vitest";

import type { ApiError, Schemas } from "@/lib/api/client";

import { checksSpentUntil, quotaWarning } from "./limits";

function apiError(status: number, code: ApiError["code"], params: ApiError["params"]): ApiError {
  return {
    type: "about:blank",
    title: code,
    status,
    code,
    detail: code,
    params,
    request_id: null,
    errors: null,
  };
}

const quota = (remaining: number): Schemas["QuotaStatus"] => ({
  checks: { limit: 10, remaining, reset_at: null },
  waveforms: { limit: 5, remaining: 5, reset_at: null },
});

it("warns from three checks left", () => {
  expect(quotaWarning(null)).toBeNull();
  expect(quotaWarning(quota(4))).toBeNull();
  expect(quotaWarning(quota(3))).toEqual({ limit: 10, remaining: 3, reset_at: null });
  expect(quotaWarning(quota(0))?.remaining).toBe(0);
});

it("counts the wait of a spent quota of checks from the refused start", () => {
  const spent = (quota: string, retry?: number) =>
    apiError(429, "RATE_LIMITED", { quota, limit: 10, retry_after_s: retry });
  expect(checksSpentUntil(spent("checks", 761), 1000)).toBe(762_000);
  expect(checksSpentUntil(spent("checks_per_ip", 5), 0)).toBe(5000);
  // Other limits are not a wait for the next check.
  expect(checksSpentUntil(spent("concurrent"), 0)).toBeNull();
  expect(checksSpentUntil(spent("waveforms", 60), 0)).toBeNull();
  expect(checksSpentUntil(spent("checks"), 0)).toBeNull();
  expect(checksSpentUntil(spent("checks", 761), null)).toBeNull();
  expect(checksSpentUntil(new Error("offline"), 0)).toBeNull();
  expect(checksSpentUntil(null, 0)).toBeNull();
});
