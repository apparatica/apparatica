"use client";

// The submissions of a guest in this browser (FR-GST-03): ids, kinds, statuses and times, newest
// first. «Мои отправки» lists them; the code and the results come from the server while it keeps
// the submission (14 days, ОВ-13). Checks write here when they start and end, the list of the server
// fills in what this browser missed, and a submission the server no longer has stays as `gone`.
import { useMemo } from "react";

import type { Schemas } from "@/lib/api/client";

import { localStore } from "./local-store";

export const SUBMISSIONS_KEY = "ap_submissions";
/** The oldest submissions are forgotten past this many. */
export const MAX_SUBMISSIONS = 500;

const UNFINISHED: ReadonlySet<string> = new Set(["queued", "running"]);

export type LocalSubmission = Pick<
  Schemas["SubmissionSummary"],
  "id" | "problem" | "version" | "kind" | "status" | "verdict_detail" | "created_at"
> & {
  /** The server no longer has it: deleted when its time ran out. */
  gone?: true;
};

const EMPTY: readonly LocalSubmission[] = Object.freeze([]);

function isSubmission(value: unknown): value is LocalSubmission {
  if (typeof value !== "object" || value === null) return false;
  const { id, problem, version, kind, status, created_at } = value as Record<string, unknown>;
  return (
    typeof id === "string" &&
    typeof problem === "string" &&
    typeof version === "number" &&
    (kind === "run" || kind === "submit") &&
    typeof status === "string" &&
    typeof created_at === "string"
  );
}

function parse(raw: string): readonly LocalSubmission[] {
  try {
    const data = JSON.parse(raw) as { v?: unknown; items?: unknown } | null;
    return data?.v === 1 && Array.isArray(data.items) ? data.items.filter(isSubmission) : EMPTY;
  } catch {
    return EMPTY;
  }
}

const store = localStore(SUBMISSIONS_KEY, parse, EMPTY);

/** All submissions of this browser, newest first. */
export const readSubmissions = (): readonly LocalSubmission[] => store.read();

function save(items: LocalSubmission[]): void {
  items.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  store.write({ v: 1, items: items.slice(0, MAX_SUBMISSIONS) }); // full or disabled: as it was
}

function local({
  id,
  problem,
  version,
  kind,
  status,
  verdict_detail,
  created_at,
}: LocalSubmission): LocalSubmission {
  return { id, problem, version, kind, status, verdict_detail, created_at };
}

/** Submissions as the server shows them now. An older list does not take a finished status back
 * to `queued`. With `complete`, the list has every submission of that problem: a finished one
 * missing from it is gone (an unfinished one may have been created after the list was read). */
export function rememberSubmissions(
  submissions: readonly LocalSubmission[],
  complete: { problem: string } | null = null,
): void {
  const items = new Map(readSubmissions().map((item) => [item.id, item]));
  let changed = false;
  for (const submission of submissions) {
    const before = items.get(submission.id);
    const stale = before !== undefined && !UNFINISHED.has(before.status);
    const next = stale && UNFINISHED.has(submission.status) ? before : local(submission);
    if (before === undefined || JSON.stringify(before) !== JSON.stringify(next)) {
      items.set(submission.id, next);
      changed = true;
    }
  }
  if (complete !== null) {
    const listed = new Set(submissions.map((item) => item.id));
    for (const item of items.values()) {
      const lost = item.problem === complete.problem && !listed.has(item.id);
      if (lost && !item.gone && !UNFINISHED.has(item.status)) {
        items.set(item.id, { ...item, gone: true });
        changed = true;
      }
    }
  }
  if (changed) save([...items.values()]);
}

/** The server answered 404 for the submission. */
export function markGone(id: string): void {
  const items = readSubmissions();
  if (!items.some((item) => item.id === id && !item.gone)) return;
  save(items.map((item) => (item.id === id ? { ...item, gone: true } : item)));
}

/** The submissions of the problem, newest first; null on the server and while the page hydrates. */
export function useSubmissionHistory(problem: string): readonly LocalSubmission[] | null {
  const items = store.useValue();
  return useMemo(
    () => (items === null ? null : items.filter((item) => item.problem === problem)),
    [items, problem],
  );
}
