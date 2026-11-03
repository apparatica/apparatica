// The limits of a guest on the problem page (FR-GST-04): the counter of checks left and the wait
// after `429 RATE_LIMITED`; the captcha after `428 CAPTCHA_REQUIRED` is read by
// features/captcha/request.ts. Pure: the components read the time and the state of useSubmission.
import { asApiError, retryAt } from "@/features/captcha/request";
import type { ApiError, Schemas } from "@/lib/api/client";

/** The counter shows from this many checks left (FR-GST-04). */
export const QUOTA_WARN_AT = 3;

/** The quotas of checks whose wait the limit panel counts down; `concurrent` has none, other
 * quotas are not about the checks of the guest. */
const WAITED_QUOTAS = new Set(["checks", "checks_per_ip"]);

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
  const found = asApiError(error);
  const quota = found?.params?.["quota"];
  if (found?.code !== "RATE_LIMITED" || typeof quota !== "string" || !WAITED_QUOTAS.has(quota))
    return null;
  return retryAt(found.params, failedAt);
}
