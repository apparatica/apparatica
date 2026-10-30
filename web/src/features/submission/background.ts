// Checks that go on after their page closed (FR-RUN-08): the stream of an unfinished check is read
// to `finalized` in the background, the result goes to the local history of the guest and a notice
// tells about it. Opening the problem again takes the check back to its page.
import { recordCheck } from "@/features/guest/history";
import { rememberSubmissions } from "@/features/guest/submissions";

import { eventsUrl, getSubmission } from "./api";
import { announceFinished } from "./finished";
import { applyEvent, type Check } from "./machine";
import { type Follower, followEvents } from "./stream";

export interface Unfinished {
  check: Check;
  /** The title of the problem, for the notice. */
  title: string;
  /** The level of the problem, for the local history. */
  difficulty: string;
}

/** One check per problem, as on its page. */
const followers = new Map<string, Follower>();

export function followInBackground({ check: started, title, difficulty }: Unfinished): void {
  const { id, problem, kind } = started;
  stopBackground(problem);
  let check = started;
  const follower = followEvents({
    url: eventsUrl(id),
    after: started.lastEventId,
    onEvent: (eventId, event) => {
      check = applyEvent(check, eventId, event);
      if (event.type !== "finalized") return;
      recordCheck({ ...check, difficulty });
      getSubmission(id).then(
        (submission) => rememberSubmissions([submission]),
        () => {}, // the list of the problem page brings it up to date later
      );
      announceFinished({ id, problem, title, kind, status: check.status }, true);
    },
    onConnection: (connection) => {
      // Over or given up: nothing more to tell.
      if (
        (connection.state === "closed" || connection.state === "failed") &&
        followers.get(problem) === follower
      ) {
        followers.delete(problem);
      }
    },
    onLost: () => {},
  });
  followers.set(problem, follower);
}

/** The page of the problem opened: it follows its check itself. */
export function stopBackground(problem: string): void {
  followers.get(problem)?.close();
  followers.delete(problem);
}

/** Tests: nothing goes on after a test. */
export function stopAllBackground(): void {
  for (const follower of followers.values()) follower.close();
  followers.clear();
}
