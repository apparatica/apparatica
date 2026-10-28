"use client";

// The shortcuts of a problem page (FR-EDT-04): Run and Submit, in the editor and outside it. A
// listener on the window in the capture phase sees them before Monaco, which binds the same keys
// to inserting a line.
import { useEffect, useEffectEvent } from "react";

import { isApple, isShortcut, type Key } from "@/lib/shortcuts";

export const RUN_KEYS: readonly Key[] = ["Mod", "Enter"];
export const SUBMIT_KEYS: readonly Key[] = ["Mod", "Shift", "Enter"];
export const UNDO_KEYS: readonly Key[] = ["Mod", "Z"];

/** The check a keydown asks for, if any. */
export function checkShortcut(event: KeyboardEvent, apple: boolean): "run" | "submit" | null {
  if (isShortcut(event, SUBMIT_KEYS, apple)) return "submit";
  if (isShortcut(event, RUN_KEYS, apple)) return "run";
  return null;
}

export function useCheckShortcuts(onCheck: (kind: "run" | "submit") => void): void {
  const check = useEffectEvent(onCheck);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      // Not from a dialog, such as the reset confirmation or the command palette.
      if (event.target instanceof Element && event.target.closest("[role=dialog]")) return;
      const kind = checkShortcut(event, isApple(navigator.userAgent));
      if (kind === null) return;
      event.preventDefault();
      event.stopPropagation();
      if (!event.repeat) check(kind);
    };
    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, []);
}
