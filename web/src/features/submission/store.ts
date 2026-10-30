// The live check of a problem page: its state and the stream that feeds it. A plain store outside
// React (useSyncExternalStore), so that events change it without effects setting state.
import { applyEvent, type Check, checkOf, isFinished, markLost, type Submission } from "./machine";
import { type Connection, type Follower, followEvents } from "./stream";

export interface SubmissionSnapshot {
  check: Check | null;
  connection: Connection | null;
}

export interface StoreOptions {
  /** The URL of the event stream of a submission. */
  eventsUrl: (id: string) => string;
  delays?: readonly number[] | undefined;
  /** `finalized` came for a check that was not finished: the check with its verdict. */
  onFinalized?: (check: Check) => void;
}

export class SubmissionStore {
  private snapshot: SubmissionSnapshot = { check: null, connection: null };
  private readonly listeners = new Set<() => void>();
  private follower: Follower | null = null;
  private attached = false;

  constructor(private readonly options: StoreOptions) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): SubmissionSnapshot => this.snapshot;

  /** A new check of this page: the previous one and its stream are dropped. */
  start(submission: Submission): void {
    this.follow(checkOf(submission));
  }

  /** The last check of the problem, found when the page opens; a check started meanwhile wins.
   * False when it did. */
  restore(submission: Submission): boolean {
    if (this.snapshot.check?.problem === submission.problem) return false;
    this.follow(checkOf(submission));
    return true;
  }

  /** "Connect now" after a lost connection. */
  reconnect(): void {
    this.follower?.reconnect();
  }

  /** The page shows `problem`: the stream runs while attached, and a check of another problem
   * is dropped. */
  attach(problem: string): void {
    this.attached = true;
    const { check } = this.snapshot;
    if (check !== null && check.problem !== problem) {
      this.set({ check: null, connection: null });
    }
    this.openStream();
  }

  detach(): void {
    this.attached = false;
    this.closeStream();
  }

  private follow(check: Check): void {
    this.closeStream();
    this.set({ check, connection: null });
    this.openStream();
  }

  private openStream(): void {
    const { check } = this.snapshot;
    if (!this.attached || check === null || this.follower !== null) return;
    if (this.snapshot.connection?.state === "closed") return;
    const { id } = check;
    // A finished check is followed too: the stream replays its console from the archive.
    const wasFinished = isFinished(check);
    this.follower = followEvents({
      url: this.options.eventsUrl(id),
      after: check.lastEventId,
      delays: this.options.delays,
      onEvent: (eventId, event) => {
        const current = this.snapshot.check;
        if (current?.id !== id) return;
        const next = applyEvent(current, eventId, event);
        this.set({ ...this.snapshot, check: next });
        if (event.type === "finalized" && !wasFinished) this.options.onFinalized?.(next);
      },
      onConnection: (connection) => {
        if (this.snapshot.check?.id === id) this.set({ ...this.snapshot, connection });
      },
      onLost: (at) => {
        const current = this.snapshot.check;
        if (current?.id === id) this.set({ ...this.snapshot, check: markLost(current, at) });
      },
    });
  }

  private closeStream(): void {
    this.follower?.close();
    this.follower = null;
  }

  private set(snapshot: SubmissionSnapshot): void {
    this.snapshot = snapshot;
    for (const listener of this.listeners) listener();
  }
}
