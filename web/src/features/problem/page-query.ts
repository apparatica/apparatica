// The state of the problem page in its address (specs/08 §1): the open tab of the left panel
// (`?tab=submissions`) and the shown submission (`?submission=<id>`). Changed without a navigation:
// the server renders the page for them only when it is opened.

export const LEFT_TABS = ["statement", "submissions"] as const;
export type LeftTab = (typeof LEFT_TABS)[number];

export const parseLeftTab = (value: unknown): LeftTab =>
  LEFT_TABS.find((tab) => tab === value) ?? "statement";

/** Sets (or with null removes) parameters of the address; the history gets no new entry. */
export function setPageQuery(changes: Record<string, string | null>): void {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  }
  if (url.href !== window.location.href) window.history.replaceState(null, "", url);
}
