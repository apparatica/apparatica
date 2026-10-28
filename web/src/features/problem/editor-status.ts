"use client";

// What the status bar shows about the editor (specs/08 §2): the cursor and the last autosave. The
// status bar is a slot of the layout, outside the page, so the page publishes them here.
import { useSyncExternalStore } from "react";

export interface EditorStatus {
  /** The cursor, from 1. */
  line: number;
  column: number;
  /** The last autosave of the draft, ISO 8601; null before the first one. */
  savedAt: string | null;
}

const INITIAL: EditorStatus = { line: 1, column: 1, savedAt: null };
const listeners = new Set<() => void>();
let status: EditorStatus | null = null;

function notify(): void {
  for (const listener of listeners) listener();
}

/** The page opened an editor (`savedAt` of its draft) or updated it. */
export function updateEditorStatus(patch: Partial<EditorStatus>): void {
  status = { ...(status ?? INITIAL), ...patch };
  notify();
}

/** The page closed. */
export function clearEditorStatus(): void {
  status = null;
  notify();
}

/** null without an open editor. */
export function readEditorStatus(): EditorStatus | null {
  return status;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** null without an open editor, on the server and while the page hydrates. */
export function useEditorStatus(): EditorStatus | null {
  return useSyncExternalStore(subscribe, readEditorStatus, () => null);
}
