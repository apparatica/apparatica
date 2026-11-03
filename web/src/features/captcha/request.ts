// The captcha the API asks for with `428 CAPTCHA_REQUIRED` (FR-GST-05, docs/api.md#капча): of a
// check on the problem page and of a login link (with the `captcha` flag). Pure.
import type { ApiError } from "@/lib/api/client";

export type CaptchaReason = "always" | "frequent" | "invalid";

export interface CaptchaRequest {
  reason: CaptchaReason;
  /** The path of a new challenge. */
  challengeUrl: `/api/v1/${string}`;
  /** Until when the captcha is needed, `Date.now()` time; null: no wait helps. */
  until: number | null;
  /** When the API asked: one request, one challenge. */
  since: number;
}

/** The error of the API, if it is one rather than a failure of the network. */
export function asApiError(error: ApiError | Error | null): ApiError | null {
  return error !== null && "code" in error ? error : null;
}

/** When the wait of `params.retry_after_s` ends, counted from `failedAt` (`Date.now()` time). */
export function retryAt(params: ApiError["params"], failedAt: number | null): number | null {
  const retry = params?.["retry_after_s"];
  return typeof retry === "number" && failedAt !== null ? failedAt + retry * 1000 : null;
}

/** The captcha the API asked for, after the start failed with 428 at `failedAt`. */
export function captchaRequest(
  error: ApiError | Error | null,
  failedAt: number | null,
): CaptchaRequest | null {
  const found = asApiError(error);
  if (found?.code !== "CAPTCHA_REQUIRED" || failedAt === null) return null;
  const reason = found.params?.["reason"];
  const url = found.params?.["challenge_url"];
  return {
    reason: reason === "always" || reason === "frequent" ? reason : "invalid",
    challengeUrl:
      typeof url === "string" && url.startsWith("/api/v1/")
        ? (url as `/api/v1/${string}`)
        : "/api/v1/captcha/challenge",
    until: retryAt(found.params, failedAt),
    since: failedAt,
  };
}
