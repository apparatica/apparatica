"use client";

// The connection of the browser to the server (specs/08 §1, sheet PageErrors): lost when the browser
// goes offline or a request to the API fails without a response. While it is lost, GET /health is
// asked again with growing pauses; the first answer brings the connection back. The network strip
// under the header and the network card of the error page show this state.
import { useSyncExternalStore } from "react";

/** Pauses before the checks in a row; the last one repeats. */
export const CHECK_DELAYS_MS = [2000, 5000, 10000, 15000, 30000] as const;

export type Connectivity =
  | { state: "online" }
  /** `attempt` is the number of the next check, at `nextAt` (`Date.now()` time); null while a
   * check runs. `dismissed`: the guest chose to work offline, the strip is hidden until the next
   * loss. */
  | { state: "offline"; attempt: number; nextAt: number | null; dismissed: boolean };

const ONLINE: Connectivity = { state: "online" };

const listeners = new Set<() => void>();
const reconnectListeners = new Set<() => void>();
let current: Connectivity = ONLINE;
let timer: ReturnType<typeof setTimeout> | undefined;
let checking: AbortController | null = null;
/** Error cards that show the loss themselves: the strip steps aside. */
let cards = 0;

function emit(): void {
  for (const listener of listeners) listener();
}

function set(next: Connectivity): void {
  const back = current.state === "offline" && next.state === "online";
  current = next;
  if (back) for (const listener of reconnectListeners) listener();
  emit();
}

function schedule(attempt: number, dismissed: boolean): void {
  const delay = CHECK_DELAYS_MS[Math.min(attempt, CHECK_DELAYS_MS.length) - 1] ?? 0;
  clearTimeout(timer);
  timer = setTimeout(() => void check(), delay);
  set({ state: "offline", attempt, nextAt: Date.now() + delay, dismissed });
}

async function check(): Promise<void> {
  if (current.state === "online") return;
  clearTimeout(timer);
  checking?.abort();
  const controller = new AbortController();
  checking = controller;
  set({ ...current, nextAt: null });
  let answered = false;
  try {
    const response = await fetch(`${location.origin}/api/v1/health`, {
      cache: "no-store",
      signal: controller.signal,
    });
    // A gateway error means the API behind it is not reachable either.
    answered = response.status < 500;
  } catch {
    // still no connection
  }
  // Changed meanwhile: by "Retry now", or by another check that got an answer.
  const now = readConnectivity();
  if (controller.signal.aborted || now.state === "online") return;
  checking = null;
  if (answered) set(ONLINE);
  else schedule(now.attempt + 1, now.dismissed);
}

/** The connection is lost: the checks begin. */
export function connectionLost(): void {
  if (typeof window === "undefined" || current.state === "offline") return;
  schedule(1, false);
}

/** A request got no response (fetch rejects with a TypeError; an abort is a DOMException). */
export function reportNetworkError(error: unknown): void {
  if (error instanceof TypeError) connectionLost();
}

/** "Retry now": checks the connection at once. */
export function checkNow(): void {
  void check();
}

/** "Work offline": hides the strip until the connection is back and lost again. */
export function dismissOffline(): void {
  if (current.state === "offline") set({ ...current, dismissed: true });
}

/** Calls `listener` each time the connection comes back; returns the unsubscribe. */
export function onReconnect(listener: () => void): () => void {
  reconnectListeners.add(listener);
  return () => reconnectListeners.delete(listener);
}

export function readConnectivity(): Connectivity {
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Online on the server and while the page hydrates. */
export function useConnectivity(): Connectivity {
  return useSyncExternalStore(subscribe, readConnectivity, () => ONLINE);
}

/** An error card that shows the loss is on the page; returns its release. */
export function claimNetworkCard(): () => void {
  cards += 1;
  emit();
  return () => {
    cards -= 1;
    emit();
  };
}

const readCards = () => cards;

/** An error card shows the loss: the strip is hidden meanwhile. */
export function useNetworkCardShown(): boolean {
  return useSyncExternalStore(subscribe, readCards, () => 0) > 0;
}

if (typeof window !== "undefined") {
  window.addEventListener("offline", connectionLost);
  // The browser has a network again: the server may answer now.
  window.addEventListener("online", checkNow);
  if (!navigator.onLine) connectionLost();
}

/** Tests: back to the first state. */
export function resetConnectivity(): void {
  clearTimeout(timer);
  checking?.abort();
  checking = null;
  cards = 0;
  reconnectListeners.clear();
  current = ONLINE;
  emit();
}
