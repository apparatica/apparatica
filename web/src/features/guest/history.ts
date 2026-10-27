"use client";

// The local history of a guest (FR-CAT-03): which problems this browser solved or tried. Checks
// write it when they end; the catalogue reads it for the statuses and the progress summary. It
// lives in localStorage, so it outlives the guest submissions on the server (14 days, ОВ-13).
import { useSyncExternalStore } from "react";

export const HISTORY_KEY = "ap_history";
const ACCEPTED: ReadonlySet<string> = new Set(["accepted", "accepted_with_warnings"]);

export type ProblemStatus = "solved" | "attempted";

export interface HistoryEntry {
  status: ProblemStatus;
  /** The level of the problem when it was checked: the progress summary counts per level. */
  difficulty: string;
}

/** By problem slug. */
export type History = Readonly<Record<string, HistoryEntry>>;

const EMPTY: History = Object.freeze({});
const listeners = new Set<() => void>();
let cached: { raw: string | null; history: History } = { raw: null, history: EMPTY };

function isEntry(value: unknown): value is HistoryEntry {
  if (typeof value !== "object" || value === null) return false;
  const { status, difficulty } = value as Record<string, unknown>;
  return (status === "solved" || status === "attempted") && typeof difficulty === "string";
}

function parse(raw: string | null): History {
  if (raw === null) return EMPTY;
  try {
    const data = JSON.parse(raw) as { v?: unknown; problems?: unknown } | null;
    const problems = data?.v === 1 ? data.problems : null;
    if (typeof problems !== "object" || problems === null) return EMPTY;
    return Object.fromEntries(Object.entries(problems).filter(([, entry]) => isEntry(entry)));
  } catch {
    return EMPTY;
  }
}

function readRaw(): string | null {
  try {
    return localStorage.getItem(HISTORY_KEY);
  } catch {
    return null; // storage disabled: no history
  }
}

/** The history of this browser; the same object while it does not change. */
export function readHistory(): History {
  const raw = readRaw();
  if (raw !== cached.raw) cached = { raw, history: parse(raw) };
  return cached.history;
}

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changed the history.
  const onStorage = (event: StorageEvent) => {
    if (event.key === HISTORY_KEY || event.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** A check of the problem ended with `status`: an accepted Submit solves it, any other check
 * tries it. A solved problem stays solved. */
export function recordCheck(check: {
  problem: string;
  difficulty: string;
  kind: "run" | "submit";
  status: string;
}): void {
  const history = readHistory();
  const before = history[check.problem];
  const solved = check.kind === "submit" && ACCEPTED.has(check.status);
  const status: ProblemStatus = solved || before?.status === "solved" ? "solved" : "attempted";
  if (before?.status === status && before.difficulty === check.difficulty) return;
  const problems = { ...history, [check.problem]: { status, difficulty: check.difficulty } };
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify({ v: 1, problems }));
  } catch {
    return; // full or disabled: the history stays as it was
  }
  notify();
}

/** The history; null on the server and while the page hydrates, where it is unknown. */
export function useHistory(): History | null {
  return useSyncExternalStore<History | null>(subscribe, readHistory, () => null);
}
