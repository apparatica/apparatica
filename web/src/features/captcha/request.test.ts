import { expect, it } from "vitest";

import type { ApiError } from "@/lib/api/client";

import { captchaRequest } from "./request";

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
