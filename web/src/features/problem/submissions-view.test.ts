import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";

import { submissionReason } from "./submissions-view";

type Failure = Schemas["FirstFailure"];
const PROBLEM = { version: 2, tests: { public: 32, hidden: 8 } };
const FAILURE: Failure = { stage: "sim_run", test: null, cycle: null };

function reason(status: string, failure: Partial<Failure> | null, extra = {}, version = 2) {
  const detail: Schemas["VerdictDetail"] = {
    first_failure: failure === null ? null : { ...FAILURE, ...failure },
    limit: null,
    warnings: [],
    error_codes: [],
    ...extra,
  };
  return submissionReason(
    { status: status as Schemas["SubmissionSummary"]["status"], version, verdict_detail: detail },
    PROBLEM,
  );
}

it("names the failed open test, out of the tests of the same version", () => {
  expect(reason("wrong_answer", { test: "t7", test_number: 7 })).toEqual({
    kind: "test",
    number: 7,
    total: 32,
  });
  expect(reason("wrong_answer", { test_number: 7 }, {}, 1)).toEqual({
    kind: "test",
    number: 7,
    total: null,
  });
  const hidden = { total: 8, passed: 2, failed_index: 3 };
  expect(reason("wrong_answer", { hidden })).toEqual({ kind: "hidden", number: 3, total: 8 });
  // Recorded before the judge told the number.
  expect(reason("wrong_answer", { test: "t7" })).toBeNull();
});

it("names the first error of a compile error or a forbidden construct", () => {
  const error = { severity: "error", message: "expected ';'", file: "solution.sv", line: 16 };
  expect(reason("compile_error", { diagnostic: error as Schemas["Diagnostic"] })).toEqual({
    kind: "line",
    line: 16,
    message: "expected ';'",
  });
  const noLine = { severity: "error", message: "$system" } as Schemas["Diagnostic"];
  expect(reason("forbidden_construct", { diagnostic: noLine })).toEqual({
    kind: "message",
    message: "$system",
  });
  expect(reason("compile_error", null)).toBeNull();
});

it("names the limit, the warnings and the codes of a platform failure", () => {
  expect(reason("limit_exceeded", {}, { limit: "output" })).toEqual({
    kind: "limit",
    limit: "output",
  });
  expect(reason("accepted_with_warnings", null, { warnings: ["lint"] })).toEqual({
    kind: "warnings",
  });
  expect(reason("internal_error", null, { error_codes: ["OUTPUT_INVALID"] })).toEqual({
    kind: "codes",
    codes: ["OUTPUT_INVALID"],
  });
  expect(reason("internal_error", null)).toBeNull();
  expect(reason("accepted", null)).toBeNull();
  expect(reason("queued", null)).toBeNull();
});
