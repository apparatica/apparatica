// A check ended where the guest does not see its results (FR-RUN-08): on another page of the site
// or in a hidden tab. The notices of the layout (finish-notices.tsx) tell about it.
import type { Status, Submission } from "./machine";

export interface FinishedCheck {
  id: string;
  problem: string;
  /** The title of the problem. */
  title: string;
  kind: Submission["kind"];
  status: Status;
}

/** `away`: the page of the problem is closed, the notice links to it. */
type Listener = (check: FinishedCheck, away: boolean) => void;

const listeners = new Set<Listener>();

export function announceFinished(check: FinishedCheck, away: boolean): void {
  for (const listener of listeners) listener(check, away);
}

export function onFinished(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
