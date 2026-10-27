"use client";

import { type ComponentProps, useSyncExternalStore } from "react";

import { formatKeys, isApple, type Key } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

const noSubscribe = () => () => {};

/** An Apple platform (⌘ instead of Ctrl). The server and the first render say no, so that
 * hydration matches; the browser answers right after. */
export function useApple(): boolean {
  return useSyncExternalStore(
    noSubscribe,
    () => isApple(navigator.userAgent),
    () => false,
  );
}

/** A hint of keys: mono 10.5 px, in the colour of its button. */
export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return <kbd className={cn("font-mono text-[10.5px] opacity-80", className)} {...props} />;
}

/** A shortcut as the platform writes it: "Ctrl ↵" or "⌘ ↵". */
export function Shortcut({ keys, ...props }: { keys: readonly Key[] } & ComponentProps<"kbd">) {
  const apple = useApple();
  return <Kbd {...props}>{formatKeys(keys, apple)}</Kbd>;
}
