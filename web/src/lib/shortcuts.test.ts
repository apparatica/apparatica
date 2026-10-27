import { expect, it } from "vitest";

import { ariaKeys, formatKeys, isApple, isShortcut } from "./shortcuts";

const key = (init: KeyboardEventInit) => new KeyboardEvent("keydown", init);

it("writes shortcuts the way the platform does", () => {
  expect(formatKeys(["Mod", "Enter"], false)).toBe("Ctrl ↵");
  expect(formatKeys(["Mod", "Shift", "Enter"], false)).toBe("Ctrl ⇧ ↵");
  expect(formatKeys(["Mod", "k"], true)).toBe("⌘ K");
  expect(ariaKeys(["Mod", "Shift", "Enter"], false)).toBe("Control+Shift+Enter");
  expect(ariaKeys(["Mod", "k"], true)).toBe("Meta+K");
  expect(isApple("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)")).toBe(true);
  expect(isApple("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe(false);
});

it("matches exactly the shortcut", () => {
  expect(isShortcut(key({ key: "k", ctrlKey: true }), ["Mod", "K"], false)).toBe(true);
  expect(isShortcut(key({ key: "K", metaKey: true }), ["Mod", "K"], true)).toBe(true);
  expect(isShortcut(key({ key: "k", metaKey: true }), ["Mod", "K"], false)).toBe(false);
  expect(isShortcut(key({ key: "k", ctrlKey: true, shiftKey: true }), ["Mod", "K"], false)).toBe(
    false,
  );
  expect(
    isShortcut(
      key({ key: "Enter", ctrlKey: true, shiftKey: true }),
      ["Mod", "Shift", "Enter"],
      false,
    ),
  ).toBe(true);
  expect(isShortcut(key({ key: "k" }), ["Mod", "K"], false)).toBe(false);
});
