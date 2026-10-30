// The title of a hidden tab tells what happened meanwhile (FR-RUN-08: the verdict of a check); the
// title comes back when the tab is shown again.
let original: string | null = null;

function restore(): void {
  if (document.visibilityState !== "visible" || original === null) return;
  document.title = original;
  original = null;
  document.removeEventListener("visibilitychange", restore);
}

/** Puts `prefix` before the title while the tab is hidden; does nothing in a visible tab. */
export function prefixHiddenTitle(prefix: string): void {
  if (document.visibilityState !== "hidden") return;
  if (original === null) {
    original = document.title;
    document.addEventListener("visibilitychange", restore);
  }
  document.title = `${prefix} · ${original}`;
}
