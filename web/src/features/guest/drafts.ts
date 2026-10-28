// Local drafts of the solutions (FR-EDT-02): the editor saves the code of a problem here a second
// after the last change and opens it again next time. One key per problem, so that saving one draft
// does not rewrite the others. Users in phase 2 keep their drafts on the server, this stays a backup.

export const DRAFT_PREFIX = "ap_draft:";

export interface Draft {
  code: string;
  /** The version of the problem the code was written for (FR-PRB-05). */
  version: number;
  /** When the draft was saved, ISO 8601. */
  savedAt: string;
}

const draftKey = (problem: string) => `${DRAFT_PREFIX}${problem}`;

function isDraft(value: unknown): value is Draft {
  if (typeof value !== "object" || value === null) return false;
  const { code, version, savedAt } = value as Record<string, unknown>;
  return (
    typeof code === "string" &&
    Number.isInteger(version) &&
    typeof savedAt === "string" &&
    !Number.isNaN(Date.parse(savedAt))
  );
}

/** The draft of the problem; null without one, or when it is broken or storage is disabled. */
export function readDraft(problem: string): Draft | null {
  try {
    const data = JSON.parse(localStorage.getItem(draftKey(problem)) ?? "null") as Record<
      string,
      unknown
    > | null;
    if (data?.["v"] !== 1) return null;
    const draft = { code: data["code"], version: data["version"], savedAt: data["savedAt"] };
    return isDraft(draft) ? draft : null;
  } catch {
    return null;
  }
}

/** Saves the code; returns the draft, or null if storage is full or disabled. */
export function writeDraft(
  problem: string,
  { code, version }: { code: string; version: number },
  now: Date = new Date(),
): Draft | null {
  const draft: Draft = { code, version, savedAt: now.toISOString() };
  try {
    localStorage.setItem(draftKey(problem), JSON.stringify({ v: 1, ...draft }));
  } catch {
    return null;
  }
  return draft;
}
