// Recorded checks of the demo problems (scripts/record_scenarios.py, docs/frontend.md). A backend
// test validates every file against the API schemas, which makes the cast below safe.
import type { Schemas } from "@/lib/api/client";

import accepted from "./scenarios/accepted.json";
import acceptedWithWarnings from "./scenarios/accepted-with-warnings.json";
import cancelled from "./scenarios/cancelled.json";
import compileError from "./scenarios/compile-error.json";
import forbiddenConstruct from "./scenarios/forbidden-construct.json";
import internalError from "./scenarios/internal-error.json";
import outputLimit from "./scenarios/output-limit.json";
import retry from "./scenarios/retry.json";
import runPassed from "./scenarios/run-passed.json";
import wrongAnswer from "./scenarios/wrong-answer.json";
import wrongAnswerHidden from "./scenarios/wrong-answer-hidden.json";

/** An event of `GET /submissions/{id}/events`: `id` is the stream entry id, milliseconds first. */
export interface StreamEvent {
  id: string;
  event: Schemas["SubmissionEvent"];
}

export interface Scenario {
  name: string;
  /** The submission after the check, as `GET /submissions/{id}` shows it. */
  submission: Schemas["Submission"];
  events: StreamEvent[];
  /** The FST trace of the failed test, base64. */
  files?: { fst: string };
}

const recorded = {
  "run-passed": runPassed,
  accepted,
  "accepted-with-warnings": acceptedWithWarnings,
  "wrong-answer": wrongAnswer,
  "wrong-answer-hidden": wrongAnswerHidden,
  "compile-error": compileError,
  "forbidden-construct": forbiddenConstruct,
  "output-limit": outputLimit,
  cancelled,
  "internal-error": internalError,
  retry,
};

export type ScenarioName = keyof typeof recorded;

export const scenarios = recorded as unknown as Record<ScenarioName, Scenario>;

export function isScenarioName(name: string): name is ScenarioName {
  return Object.hasOwn(recorded, name);
}
