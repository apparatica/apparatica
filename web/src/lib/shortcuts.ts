// Keyboard shortcuts: how they are shown (Ctrl or ⌘), announced (aria-keyshortcuts) and matched.
// `Mod` is Ctrl, and ⌘ on Apple platforms.

export type Key = "Mod" | "Shift" | "Alt" | "Enter" | "Escape" | (string & {});

const SHOWN: Record<string, { mac: string; other: string }> = {
  Mod: { mac: "⌘", other: "Ctrl" },
  Shift: { mac: "⇧", other: "⇧" },
  Alt: { mac: "⌥", other: "Alt" },
  Enter: { mac: "↵", other: "↵" },
  Escape: { mac: "Esc", other: "Esc" },
};

export function isApple(platform: string): boolean {
  return /mac|iphone|ipad|ipod/i.test(platform);
}

/** "Ctrl ⇧ ↵" or "⌘ ⇧ ↵". */
export function formatKeys(keys: readonly Key[], apple: boolean): string {
  return keys.map((key) => SHOWN[key]?.[apple ? "mac" : "other"] ?? key.toUpperCase()).join(" ");
}

/** The value of aria-keyshortcuts: "Control+Shift+Enter". */
export function ariaKeys(keys: readonly Key[], apple: boolean): string {
  return keys
    .map((key) =>
      key === "Mod" ? (apple ? "Meta" : "Control") : key.length === 1 ? key.toUpperCase() : key,
    )
    .join("+");
}

/** Whether a keydown is exactly this shortcut (no other modifiers). */
export function isShortcut(event: KeyboardEvent, keys: readonly Key[], apple: boolean): boolean {
  const wants = new Set(keys);
  const mod = apple ? event.metaKey : event.ctrlKey;
  const other = apple ? event.ctrlKey : event.metaKey;
  if (mod !== wants.has("Mod") || other) return false;
  if (event.shiftKey !== wants.has("Shift") || event.altKey !== wants.has("Alt")) return false;
  const [main] = keys.filter((key) => !["Mod", "Shift", "Alt"].includes(key));
  return main !== undefined && event.key.toLowerCase() === main.toLowerCase();
}
