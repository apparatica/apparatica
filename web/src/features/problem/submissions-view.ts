// The short reason of a submission in «Мои отправки» (FR-PRB-06): where it failed, from the
// verdict of the list alone — the stages are not read for it.
import type { LocalSubmission } from "@/features/guest/submissions";
import type { Schemas } from "@/lib/api/client";

import { OPEN_GROUP } from "./pipeline-view";

export type SubmissionReason =
  /** An open test, "тест 7 из 32"; without the total when the version had other tests. */
  | { kind: "test"; number: number; total: number | null }
  | { kind: "hidden"; number: number; total: number }
  /** The first error of a compile error or a forbidden construct. */
  | { kind: "line"; line: number; message: string }
  | { kind: "message"; message: string }
  | { kind: "limit"; limit: NonNullable<Schemas["VerdictDetail"]["limit"]> }
  | { kind: "warnings" }
  | { kind: "codes"; codes: string[] };

export function submissionReason(
  submission: Pick<LocalSubmission, "status" | "version" | "verdict_detail">,
  problem: { version: number; tests: Record<string, number> },
): SubmissionReason | null {
  const detail = submission.verdict_detail;
  const failure = detail?.first_failure ?? null;
  switch (submission.status) {
    case "wrong_answer": {
      if (failure?.test_number != null) {
        const sameTests = submission.version === problem.version;
        const total = sameTests ? (problem.tests[OPEN_GROUP] ?? null) : null;
        return { kind: "test", number: failure.test_number, total };
      }
      const hidden = failure?.hidden;
      if (hidden?.failed_index != null) {
        return { kind: "hidden", number: hidden.failed_index, total: hidden.total };
      }
      return null;
    }
    case "compile_error":
    case "forbidden_construct": {
      const error = failure?.diagnostic;
      if (error == null) return null;
      return error.line == null
        ? { kind: "message", message: error.message }
        : { kind: "line", line: error.line, message: error.message };
    }
    case "limit_exceeded":
      return detail?.limit == null ? null : { kind: "limit", limit: detail.limit };
    case "accepted_with_warnings":
      return { kind: "warnings" };
    case "internal_error":
      return detail?.error_codes.length ? { kind: "codes", codes: detail.error_codes } : null;
    default:
      return null;
  }
}
