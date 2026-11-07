// The code of a problem page (FR-EDT-02/03, FR-PRB-05): what the editor opens with, the autosave of
// the draft a second after the last change, the reset to the template and the notice that the
// problem changed since the draft was written. A plain store outside React (useSyncExternalStore),
// so that the editor events change it without effects setting state.
//
// A signed-in user's draft is saved on the server as well, the local one stays as the backup: the
// editor opens with the newer of the two, a draft of another device or of this browser before the
// login. One save is sent at a time, the newest code after it; a closed tab sends its last one at
// once. A failed save waits for the next change.
import type { editor } from "monaco-editor/editor";

import { type Draft, readDraft, writeDraft } from "@/features/guest/drafts";

import { updateEditorStatus } from "./editor-status";
import { type AccountDrafts, isSignedOut, saveServerDraft, type ServerDraft } from "./server-draft";

export const AUTOSAVE_DELAY_MS = 1000;

/** What the workspace needs of Monaco. */
export type SolutionEditor = Pick<
  editor.IStandaloneCodeEditor,
  | "getValue"
  | "getModel"
  | "executeEdits"
  | "pushUndoStop"
  | "onDidChangeModelContent"
  | "onDidChangeCursorPosition"
  | "focus"
  | "setPosition"
  | "revealLineInCenter"
>;

export interface WorkspaceSnapshot {
  /** The editor is open. */
  ready: boolean;
  /** The last autosave, ISO 8601; null before the first one. */
  savedAt: string | null;
  /** The draft was written for this older version of the problem. */
  draftVersion: number | null;
}

export interface WorkspaceOptions {
  problem: string;
  /** The current version: drafts are saved for it. */
  version: number;
  template: string;
  delayMs?: number;
  /** The drafts of a signed-in user on the server; null for a guest. */
  account?: AccountDrafts | null;
  /** Saves on the server; saveServerDraft by default. */
  saveRemote?: typeof saveServerDraft;
}

type Code = Pick<Draft, "code" | "version">;

export class Workspace {
  private snapshot: WorkspaceSnapshot = { ready: false, savedAt: null, draftVersion: null };
  private readonly listeners = new Set<() => void>();
  private draft: Draft | null | undefined;
  /** Code opened before the editor loaded. */
  private opened: string | null = null;
  private editor: SolutionEditor | null = null;
  private disposers: (() => void)[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly delayMs: number;
  /** Saves to the server; null for a guest and once the session has ended. */
  private saveRemote: typeof saveServerDraft | null;
  private sending = false;
  /** The code to send after the save in flight. */
  private next: Code | null = null;

  constructor(private readonly options: WorkspaceOptions) {
    this.delayMs = options.delayMs ?? AUTOSAVE_DELAY_MS;
    this.saveRemote = options.account ? (options.saveRemote ?? saveServerDraft) : null;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): WorkspaceSnapshot => this.snapshot;

  /** The code the editor opens with: the draft, or the template without one. */
  initialCode(): string {
    return this.opened ?? this.readDraft()?.code ?? this.options.template;
  }

  /** The code to check: the editor, or what it is about to open with. */
  code(): string {
    return this.editor?.getValue() ?? this.initialCode();
  }

  /** The editor opened with `initialCode()`. */
  attach(editor: SolutionEditor): void {
    this.detach();
    this.editor = editor;
    const draft = this.readDraft();
    const outdated = draft !== null && draft.version < this.options.version;
    this.set({
      ready: true,
      savedAt: draft?.savedAt ?? null,
      draftVersion: outdated ? draft.version : null,
    });
    updateEditorStatus({ line: 1, column: 1, savedAt: draft?.savedAt ?? null });
    const content = editor.onDidChangeModelContent(() => this.schedule());
    const cursor = editor.onDidChangeCursorPosition(({ position }) =>
      updateEditorStatus({ line: position.lineNumber, column: position.column }),
    );
    // A closed tab does not wait for the timer.
    const onPageHide = () => this.flush(true);
    window.addEventListener("pagehide", onPageHide);
    this.disposers = [
      () => content.dispose(),
      () => cursor.dispose(),
      () => window.removeEventListener("pagehide", onPageHide),
    ];
  }

  /** The editor closes: a pending change is saved now. */
  detach(): void {
    this.flush();
    for (const dispose of this.disposers) dispose();
    this.disposers = [];
    this.editor = null;
    if (this.snapshot.ready) this.set({ ...this.snapshot, ready: false });
  }

  /** Replaces the code with the template as one edit, so Ctrl+Z brings the code back. */
  reset(): void {
    this.replace(this.options.template);
  }

  /** Replaces the code with `code` (the template, the code of a submission) as one edit, so
   * Ctrl+Z brings the code back. The draft is saved for the current version. */
  replace(code: string): void {
    const editor = this.editor;
    const model = editor?.getModel();
    if (editor == null || model == null) {
      // The editor is still loading: it opens with the code, saved as the draft if it can be.
      this.opened = code;
      this.store({ code, version: this.options.version });
      this.set({ ...this.snapshot }); // the editor renders again with it
      return;
    }
    editor.pushUndoStop();
    editor.executeEdits("replace", [
      { range: model.getFullModelRange(), text: code, forceMoveMarkers: true },
    ]);
    editor.pushUndoStop();
    editor.focus();
    this.acknowledge();
  }

  /** Moves the focus to the editor: «Перейти к редактору» of the locked solutions. */
  focus(): void {
    this.editor?.focus();
  }

  /** Puts the cursor on a line of the solution and scrolls to it: links in the results. */
  reveal(line: number, column = 1): void {
    const editor = this.editor;
    if (editor === null) return;
    editor.setPosition({ lineNumber: line, column });
    editor.revealLineInCenter(line);
    editor.focus();
  }

  /** The notice about the new version was read: the draft is saved for the current version. */
  acknowledge(): void {
    if (this.snapshot.draftVersion === null) return;
    this.set({ ...this.snapshot, draftVersion: null });
    this.save();
  }

  /** Saves a pending change now; `closing`: the tab is closing. */
  flush(closing = false): void {
    if (this.timer === null) return;
    clearTimeout(this.timer);
    this.timer = null;
    this.save(closing);
  }

  private schedule(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.save();
    }, this.delayMs);
  }

  private save(closing = false): void {
    if (this.editor === null) return;
    this.store({ code: this.editor.getValue(), version: this.options.version }, closing);
  }

  /** Saves the code locally and on the server. The indicator shows the local save, or the one
   * of the server when storage is full or disabled. */
  private store(code: Code, closing = false): void {
    const saved = writeDraft(this.options.problem, code);
    if (saved !== null) {
      this.draft = saved;
      this.saved(saved.savedAt);
    }
    this.send(code, closing, saved === null);
  }

  private send(code: Code, closing: boolean, showSaved: boolean): void {
    const save = this.saveRemote;
    if (save === null) return;
    if (this.sending && !closing) {
      this.next = code;
      return;
    }
    this.next = null; // older than this code
    this.sending = true;
    save(this.options.problem, code, { keepalive: closing }).then(
      (draft) => {
        if (showSaved) this.saved(draft.updated_at);
        this.sent();
      },
      (error: unknown) => {
        if (isSignedOut(error)) this.saveRemote = null; // the local draft goes on
        this.sent();
      },
    );
  }

  private sent(): void {
    this.sending = false;
    const next = this.next;
    this.next = null;
    if (next !== null) this.send(next, false, false);
  }

  private saved(savedAt: string): void {
    this.set({ ...this.snapshot, savedAt });
    updateEditorStatus({ savedAt });
  }

  private readDraft(): Draft | null {
    // Read once: later the editor holds the code.
    if (this.draft === undefined) {
      this.draft = newer(readDraft(this.options.problem), this.options.account?.draft ?? null);
    }
    return this.draft;
  }

  private set(snapshot: WorkspaceSnapshot): void {
    this.snapshot = snapshot;
    for (const listener of this.listeners) listener();
  }
}

/** The newer of the local draft and the one of the server; the clocks of the browser and of the
 * server differ a little, which matters only for saves seconds apart on two devices. */
function newer(local: Draft | null, server: ServerDraft | null): Draft | null {
  if (server === null) return local;
  const remote: Draft = {
    code: server.code,
    version: server.problem_version,
    savedAt: server.updated_at,
  };
  if (local === null) return remote;
  return Date.parse(remote.savedAt) > Date.parse(local.savedAt) ? remote : local;
}
