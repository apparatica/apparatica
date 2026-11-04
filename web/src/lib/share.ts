// Giving a link away: the share sheet of the system (Web Share) where there is one, else the
// clipboard.

export const canShare = (): boolean => typeof navigator.share === "function";

export type Shared = "shared" | "copied" | "cancelled" | "failed";

export async function copyLink(url: string): Promise<Shared> {
  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}

/** Closing the sheet is not a failure; a refused share falls back to the copy. */
export async function shareLink(title: string, url: string): Promise<Shared> {
  if (!canShare()) return copyLink(url);
  try {
    await navigator.share({ title, url });
    return "shared";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return "cancelled";
    return copyLink(url);
  }
}
