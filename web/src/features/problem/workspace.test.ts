import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { readDraft, writeDraft } from "@/features/guest/drafts";

import { clearEditorStatus, readEditorStatus } from "./editor-status";
import { type SolutionEditor, Workspace } from "./workspace";

const TEMPLATE = "module sync_fifo;\n  // Ваше решение\nendmodule\n";

type Listener<T> = (event: T) => void;
type CursorEvent = { position: { lineNumber: number; column: number } };

/** Monaco as far as the workspace sees it: the text, the undo stops and the change events. */
class FakeEditor {
  undoStops = 0;
  edits: unknown[] = [];
  focused = false;
  position: { lineNumber: number; column: number } | null = null;
  revealed: number | null = null;
  private readonly content = new Set<Listener<unknown>>();
  private readonly cursor = new Set<Listener<CursorEvent>>();

  constructor(public value: string) {}

  type(text: string) {
    this.value += text;
    for (const listener of this.content) listener({});
  }

  move(lineNumber: number, column: number) {
    for (const listener of this.cursor) listener({ position: { lineNumber, column } });
  }

  get listeners() {
    return this.content.size + this.cursor.size;
  }

  asEditor(): SolutionEditor {
    const subscribe =
      <T>(set: Set<Listener<T>>) =>
      (listener: Listener<T>) => {
        set.add(listener);
        return { dispose: () => set.delete(listener) };
      };
    const editor = {
      getValue: () => this.value,
      getModel: () => ({ getFullModelRange: () => "all" }),
      executeEdits: (_source: string, edits: { text: string }[]) => {
        this.edits.push(...edits);
        this.value = edits[0]?.text ?? this.value;
        return true;
      },
      pushUndoStop: () => {
        this.undoStops += 1;
        return true;
      },
      onDidChangeModelContent: subscribe(this.content),
      onDidChangeCursorPosition: subscribe(this.cursor),
      focus: () => {
        this.focused = true;
      },
      setPosition: (position: { lineNumber: number; column: number }) => {
        this.position = position;
      },
      revealLineInCenter: (line: number) => {
        this.revealed = line;
      },
    };
    return editor as unknown as SolutionEditor;
  }
}

beforeEach(() => {
  vi.useFakeTimers({
    now: new Date("2026-10-28T09:30:00Z"),
    toFake: ["setTimeout", "clearTimeout", "Date"],
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  clearEditorStatus();
});

const workspace = () => new Workspace({ problem: "sync-fifo", version: 2, template: TEMPLATE });

it("opens the template, saves a second after the last change and shows the time", () => {
  const space = workspace();
  expect(space.initialCode()).toBe(TEMPLATE);
  const editor = new FakeEditor(space.initialCode());
  space.attach(editor.asEditor());
  expect(space.getSnapshot()).toEqual({ ready: true, savedAt: null, draftVersion: null });
  expect(readEditorStatus()).toEqual({ line: 1, column: 1, savedAt: null });

  editor.type("a");
  vi.advanceTimersByTime(600);
  editor.type("b");
  vi.advanceTimersByTime(900);
  expect(readDraft("sync-fifo")).toBeNull();
  vi.advanceTimersByTime(100);
  expect(readDraft("sync-fifo")).toMatchObject({ code: `${TEMPLATE}ab`, version: 2 });
  expect(space.getSnapshot().savedAt).toBe("2026-10-28T09:30:01.600Z");
  expect(readEditorStatus()?.savedAt).toBe("2026-10-28T09:30:01.600Z");

  editor.move(3, 7);
  expect(readEditorStatus()).toMatchObject({ line: 3, column: 7 });
  expect(space.code()).toBe(`${TEMPLATE}ab`);
});

it("opens the draft and saves a pending change when the editor closes", () => {
  writeDraft("sync-fifo", { code: "draft", version: 2 }, new Date("2026-10-27T18:00:00Z"));
  const space = workspace();
  expect(space.initialCode()).toBe("draft");
  expect(space.code()).toBe("draft"); // before the editor opens
  const editor = new FakeEditor(space.initialCode());
  space.attach(editor.asEditor());
  expect(space.getSnapshot().savedAt).toBe("2026-10-27T18:00:00.000Z");

  editor.type("!");
  space.detach();
  expect(readDraft("sync-fifo")?.code).toBe("draft!");
  expect(editor.listeners).toBe(0);
  expect(space.getSnapshot().ready).toBe(false);
});

it("saves a pending change when the tab closes", () => {
  const space = workspace();
  const editor = new FakeEditor(TEMPLATE);
  space.attach(editor.asEditor());
  editor.type("x");
  window.dispatchEvent(new Event("pagehide"));
  expect(readDraft("sync-fifo")?.code).toBe(`${TEMPLATE}x`);
});

it("resets to the template as one undoable edit and focuses the editor", () => {
  writeDraft("sync-fifo", { code: "draft", version: 2 });
  const space = workspace();
  const editor = new FakeEditor(space.initialCode());
  space.attach(editor.asEditor());
  space.reset();
  expect(editor.value).toBe(TEMPLATE);
  expect(editor.edits).toEqual([{ range: "all", text: TEMPLATE, forceMoveMarkers: true }]);
  expect(editor.undoStops).toBe(2);
  expect(editor.focused).toBe(true);
});

it("puts the cursor on a line and shows it", () => {
  const space = workspace();
  space.reveal(3); // no editor yet: nothing to do
  const editor = new FakeEditor(space.initialCode());
  space.attach(editor.asEditor());
  space.reveal(3, 5);
  expect(editor.position).toEqual({ lineNumber: 3, column: 5 });
  expect(editor.revealed).toBe(3);
  expect(editor.focused).toBe(true);
});

it("knows a draft of an older version until the notice is read", () => {
  writeDraft("sync-fifo", { code: "old", version: 1 });
  const space = workspace();
  space.attach(new FakeEditor(space.initialCode()).asEditor());
  expect(space.getSnapshot().draftVersion).toBe(1);

  space.acknowledge();
  expect(space.getSnapshot().draftVersion).toBeNull();
  expect(readDraft("sync-fifo")).toMatchObject({ code: "old", version: 2 });
});

it("keeps the indicator when the storage is full", () => {
  const space = workspace();
  const editor = new FakeEditor(TEMPLATE);
  space.attach(editor.asEditor());
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("full", "QuotaExceededError");
  });
  editor.type("x");
  vi.advanceTimersByTime(1000);
  expect(space.getSnapshot().savedAt).toBeNull();
});
