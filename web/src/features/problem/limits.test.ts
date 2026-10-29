import { expect, it } from "vitest";

import type { ApiError, Schemas } from "@/lib/api/client";

import { captchaRequest, checksSpentUntil, formatCountdown, quotaWarning } from "./limits";

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

it("reads the captcha the API asks for", () => {
  const needed = (params: Record<string, unknown>) =>
    apiError(428, "CAPTCHA_REQUIRED", { challenge_url: "/api/v1/captcha/challenge", ...params });
  expect(captchaRequest(needed({ reason: "frequent", retry_after_s: 42 }), 1000)).toEqual({
    reason: "frequent",
    challengeUrl: "/api/v1/captcha/challenge",
    until: 43_000,
    since: 1000,
  });
  expect(captchaRequest(needed({ reason: "always" }), 0)).toMatchObject({
    reason: "always",
    until: null,
  });
  // An unknown reason asks again; a foreign URL is not followed.
  expect(
    captchaRequest(needed({ reason: "new", challenge_url: "https://evil.example/" }), 0),
  ).toMatchObject({ reason: "invalid", challengeUrl: "/api/v1/captcha/challenge" });
  expect(captchaRequest(needed({ reason: "always" }), null)).toBeNull();
  expect(captchaRequest(apiError(429, "RATE_LIMITED", null), 0)).toBeNull();
});

it("formats a wait as a timer", () => {
  expect(formatCountdown(42_000)).toBe("0:42");
  expect(formatCountdown(41_001)).toBe("0:42"); // whole seconds, up
  expect(formatCountdown(761_000)).toBe("12:41");
  expect(formatCountdown(3_723_000)).toBe("1:02:03");
  expect(formatCountdown(-5)).toBe("0:00");
});
