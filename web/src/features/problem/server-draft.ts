// Drafts of a signed-in user on the server (FR-EDT-02, docs/api.md): the page reads the draft when
// it is rendered (`loadServerDraft`), the editor saves it with the local one, which stays as the
// backup.
import { browserApi } from "@/lib/api/browser";
import type { ApiError, Schemas } from "@/lib/api/client";

export type ServerDraft = Schemas["Draft"];

/** What the page knows of the drafts of the user: null for a guest (or an ended session). */
export interface AccountDrafts {
  /** The draft of the problem when the page was rendered; null without one. */
  draft: ServerDraft | null;
}

/** In the browser: `keepalive` lets the request outlive a closed tab. */
export async function saveServerDraft(
  slug: string,
  draft: { code: string; version: number },
  { keepalive = false }: { keepalive?: boolean } = {},
): Promise<ServerDraft> {
  const { data, error } = await browserApi.PUT("/api/v1/me/drafts/{slug}", {
    params: { path: { slug } },
    body: { code: draft.code, problem_version: draft.version },
    keepalive,
  });
  if (error !== undefined) throw error;
  return data;
}

export const isSignedOut = (error: unknown): boolean =>
  typeof error === "object" && error !== null && (error as ApiError).code === "UNAUTHENTICATED";
