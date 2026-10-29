// The limits of a guest on the problem page (FR-GST-04, FR-GST-05): the counter of checks left, the
// wait after `429 RATE_LIMITED`, the captcha after `428 CAPTCHA_REQUIRED`. Pure: the components
// read the time and the state of useSubmission.
import type { ApiError, Schemas } from "@/lib/api/client";

/** The counter shows from this many checks left (FR-GST-04). */
export const QUOTA_WARN_AT = 3;

/** The quotas of checks whose wait the limit panel counts down; `concurrent` has none, other
 * quotas are not about the checks of the guest. */
const WAITED_QUOTAS = new Set(["checks", "checks_per_ip"]);

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

function apiError(error: ApiError | Error | null): ApiError | null {
  return error !== null && "code" in error ? error : null;
}

function waitOf(params: ApiError["params"], failedAt: number | null): number | null {
  const retry = params?.["retry_after_s"];
  return typeof retry === "number" && failedAt !== null ? failedAt + retry * 1000 : null;
}

/** The checks left this hour, when the counter shows them; null otherwise. */
export function quotaWarning(quota: Schemas["QuotaStatus"] | null): Schemas["QuotaWindow"] | null {
  return quota !== null && quota.checks.remaining <= QUOTA_WARN_AT ? quota.checks : null;
}

/** Until when checks are spent (`Date.now()` time), after the start failed with 429 at
 * `failedAt`; null when this is not a spent quota of checks. */
export function checksSpentUntil(
  error: ApiError | Error | null,
  failedAt: number | null,
): number | null {
  const found = apiError(error);
  const quota = found?.params?.["quota"];
  if (found?.code !== "RATE_LIMITED" || typeof quota !== "string" || !WAITED_QUOTAS.has(quota))
    return null;
  return waitOf(found.params, failedAt);
}

/** The captcha the API asked for, after the start failed with 428 at `failedAt`. */
export function captchaRequest(
  error: ApiError | Error | null,
  failedAt: number | null,
): CaptchaRequest | null {
  const found = apiError(error);
  if (found?.code !== "CAPTCHA_REQUIRED" || failedAt === null) return null;
  const reason = found.params?.["reason"];
  const url = found.params?.["challenge_url"];
  return {
    reason: reason === "always" || reason === "frequent" ? reason : "invalid",
    challengeUrl:
      typeof url === "string" && url.startsWith("/api/v1/")
        ? (url as `/api/v1/${string}`)
        : "/api/v1/captcha/challenge",
    until: waitOf(found.params, failedAt),
    since: failedAt,
  };
}

/** A wait as a timer: "0:42", "12:41", "1:02:03"; whole seconds, rounded up. */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}`
    : `${minutes}:${seconds}`;
}
