import { expect, it } from "vitest";

import { checkShortcut } from "./shortcuts";

const key = (init: KeyboardEventInit) => new KeyboardEvent("keydown", { key: "Enter", ...init });

it("asks for Run on Ctrl+Enter and for Submit with Shift", () => {
  expect(checkShortcut(key({ ctrlKey: true }), false)).toBe("run");
  expect(checkShortcut(key({ ctrlKey: true, shiftKey: true }), false)).toBe("submit");
  expect(checkShortcut(key({}), false)).toBeNull();
  expect(checkShortcut(key({ ctrlKey: true, altKey: true }), false)).toBeNull();
  expect(checkShortcut(key({ ctrlKey: true, key: "s" }), false)).toBeNull();
});

it("uses ⌘ on Apple platforms", () => {
  expect(checkShortcut(key({ metaKey: true }), true)).toBe("run");
  expect(checkShortcut(key({ metaKey: true, shiftKey: true }), true)).toBe("submit");
  expect(checkShortcut(key({ ctrlKey: true }), true)).toBeNull();
});
