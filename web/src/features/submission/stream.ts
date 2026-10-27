// Following the event stream of a check (specs/07 §4.2): a dropped connection is resumed after the
// last event id with backoff; after the last delay the client waits for "connect now" (FR-CON-05).
import type { ApiError } from "@/lib/api/client";

import type { SubmissionEvent } from "./machine";
import { readSse } from "./sse";

/** Delays of the reconnects in a row; one more failure and the stream gives up. */
export const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 15000] as const;

export type Connection =
  /** `lostAt` is set while the stream is being restored after a loss. */
  | { state: "connecting"; lostAt: number | null }
  | { state: "open" }
  /** Reconnect number `retry` at `at`. */
  | { state: "waiting"; retry: number; at: number; lostAt: number }
  /** Given up: `error` when the API refused the stream (the submission is gone). */
  | { state: "failed"; lostAt: number | null; error: ApiError | null }
  /** `finalized` came: the stream is over. */
  | { state: "closed" };

export interface FollowOptions {
  url: string;
  /** Resume after this event id; null replays the whole stream. */
  after: string | null;
  delays?: readonly number[] | undefined;
  onEvent: (id: string | null, event: SubmissionEvent) => void;
  onConnection: (connection: Connection) => void;
  /** The connection was lost at `at`: once per loss, not per reconnect. */
  onLost: (at: number) => void;
}

export interface Follower {
  /** Connect now: "connect now" while waiting or after giving up. */
  reconnect(): void;
  close(): void;
}

async function apiError(response: Response): Promise<ApiError | null> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return null;
  }
}

export function followEvents(options: FollowOptions): Follower {
  const { url, delays = RECONNECT_DELAYS_MS, onEvent, onConnection, onLost } = options;
  let after = options.after;
  let retry = 0;
  let lostAt: number | null = null;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;

  async function connect() {
    clearTimeout(timer);
    controller?.abort();
    const current = new AbortController();
    controller = current;
    onConnection({ state: "connecting", lostAt });
    let finalized = false;
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      if (after !== null) headers["Last-Event-ID"] = after;
      const response = await fetch(url, { headers, signal: current.signal, cache: "no-store" });
      if (response.status === 404) {
        // The submission is gone (deleted by retention, or the guest cookie changed).
        closed = true;
        onConnection({ state: "failed", lostAt, error: await apiError(response) });
        return;
      }
      if (!response.ok || response.body === null) throw new Error(`HTTP ${response.status}`);
      onConnection({ state: "open" });
      for await (const message of readSse(response.body)) {
        const event = JSON.parse(message.data) as SubmissionEvent;
        if (message.id !== null) after = message.id;
        retry = 0;
        lostAt = null;
        onEvent(message.id, event);
        if (event.type === "finalized") {
          finalized = true;
          break;
        }
      }
    } catch {
      // A network error, a refused stream or a broken event: resumed as a drop.
    }
    if (current.signal.aborted || closed) return;
    if (finalized) {
      closed = true;
      onConnection({ state: "closed" });
      return;
    }
    if (lostAt === null) {
      lostAt = Date.now();
      onLost(lostAt);
    }
    const delay = delays[retry];
    if (delay === undefined) {
      onConnection({ state: "failed", lostAt, error: null });
      return;
    }
    retry += 1;
    onConnection({ state: "waiting", retry, at: Date.now() + delay, lostAt });
    timer = setTimeout(() => void connect(), delay);
  }

  void connect();
  return {
    reconnect() {
      if (closed) return;
      retry = 0;
      void connect();
    },
    close() {
      closed = true;
      clearTimeout(timer);
      controller?.abort();
    },
  };
}
