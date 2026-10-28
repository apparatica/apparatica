// The code of a problem page (FR-EDT-02/03, FR-PRB-05): what the editor opens with, the autosave of
// the draft a second after the last change, the reset to the template and the notice that the
// problem changed since the draft was written. A plain store outside React (useSyncExternalStore),
// so that the editor events change it without effects setting state.
import type { editor } from "monaco-editor/editor";

import { type Draft, readDraft, writeDraft } from "@/features/guest/drafts";

import { updateEditorStatus } from "./editor-status";

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
}

export class Workspace {
  private snapshot: WorkspaceSnapshot = { ready: false, savedAt: null, draftVersion: null };
  private readonly listeners = new Set<() => void>();
  private draft: Draft | null | undefined;
  private editor: SolutionEditor | null = null;
  private disposers: (() => void)[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly delayMs: number;

  constructor(private readonly options: WorkspaceOptions) {
    this.delayMs = options.delayMs ?? AUTOSAVE_DELAY_MS;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): WorkspaceSnapshot => this.snapshot;

  /** The code the editor opens with: the draft, or the template without one. */
  initialCode(): string {
    return this.readDraft()?.code ?? this.options.template;
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
    const onPageHide = () => this.flush();
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
    const editor = this.editor;
    const model = editor?.getModel();
    if (editor == null || model == null) return;
    editor.pushUndoStop();
    editor.executeEdits("reset", [
      { range: model.getFullModelRange(), text: this.options.template, forceMoveMarkers: true },
    ]);
    editor.pushUndoStop();
    editor.focus();
    this.acknowledge();
  }

  /** The notice about the new version was read: the draft is saved for the current version. */
  acknowledge(): void {
    if (this.snapshot.draftVersion === null) return;
    this.set({ ...this.snapshot, draftVersion: null });
    this.save();
  }

  /** Saves a pending change now. */
  flush(): void {
    if (this.timer === null) return;
    clearTimeout(this.timer);
    this.timer = null;
    this.save();
  }

  private schedule(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.save();
    }, this.delayMs);
  }

  private save(): void {
    if (this.editor === null) return;
    const saved = writeDraft(this.options.problem, {
      code: this.editor.getValue(),
      version: this.options.version,
    });
    if (saved === null) return; // storage full or disabled: the indicator keeps the last save
    this.draft = saved;
    this.set({ ...this.snapshot, savedAt: saved.savedAt });
    updateEditorStatus({ savedAt: saved.savedAt });
  }

  private readDraft(): Draft | null {
    // Read once: later the editor holds the code.
    if (this.draft === undefined) this.draft = readDraft(this.options.problem);
    return this.draft;
  }

  private set(snapshot: WorkspaceSnapshot): void {
    this.snapshot = snapshot;
    for (const listener of this.listeners) listener();
  }
}
