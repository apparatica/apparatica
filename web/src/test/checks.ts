// Checks of the recorded scenarios at any point of their stream: for the tests of the results.
import { applyEvent, type Check, checkOf } from "@/features/submission/machine";
import type { Scenario } from "@/mocks/scenarios";

/** The check as POST /submissions returns it: queued, nothing run yet. */
export function queuedCheck(scenario: Scenario): Check {
  return checkOf({
    ...scenario.submission,
    status: "queued",
    verdict_detail: null,
    finished_at: null,
    started_at: null,
    queue_position: 3,
    eta_s: 10,
    stages: [],
    artifacts: [],
  });
}

/** The check after `events`; each comes at `now`. */
export function foldEvents(check: Check, events: Scenario["events"], now = 0): Check {
  return events.reduce(
    (state, { id, event }) => applyEvent(state, event.type === "queue" ? null : id, event, now),
    check,
  );
}

/** The check of a scenario after its first `count` events (all of them by default). */
export function playCheck(scenario: Scenario, count = scenario.events.length, now = 0): Check {
  return foldEvents(queuedCheck(scenario), scenario.events.slice(0, count), now);
}

/** The number of events of a scenario up to and including the first one that matches. */
export function eventsUntil(
  scenario: Scenario,
  match: (event: Scenario["events"][number]["event"]) => boolean,
): number {
  const index = scenario.events.findIndex(({ event }) => match(event));
  if (index === -1) throw new Error(`no such event in ${scenario.name}`);
  return index + 1;
}
