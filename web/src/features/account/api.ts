// Requests of the own account (docs/api.md#пользователи-и-вход-ф2-контракт): who is signed in, the
// nick and the name, deletion and export, login by a link from a letter, logout.
import { browserApi as api } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";

export type Me = Schemas["Me"];

export const meKey = ["me"] as const;

/** The signed-in user; null for a guest. */
export async function getMe(): Promise<Me | null> {
  const { data, error, response } = await api.GET("/api/v1/me");
  if (response.status === 401) return null;
  if (error !== undefined) throw error;
  return data;
}

export async function updateMe(body: Schemas["MeUpdate"]): Promise<Me> {
  const { data, error } = await api.PATCH("/api/v1/me", { body });
  if (error !== undefined) throw error;
  return data;
}

/** Asks to delete the account in 7 days (FR-USR-05); asking again keeps the time. */
export async function deleteMe(): Promise<Me> {
  const { data, error } = await api.DELETE("/api/v1/me");
  if (error !== undefined) throw error;
  return data;
}

/** Cancels the deletion of the account. */
export async function restoreMe(): Promise<Me> {
  const { data, error } = await api.POST("/api/v1/me/restore");
  if (error !== undefined) throw error;
  return data;
}

/** The own data (FR-USR-05) and the name of its file, `apparatica-<nick>.json`. */
export async function exportMe(): Promise<{ file: Blob; name: string }> {
  const { data, error, response } = await api.GET("/api/v1/me/export", { parseAs: "blob" });
  if (error !== undefined) throw error;
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "apparatica.json";
  return { file: data, name };
}

/** Loads the page anew after a logout, as a guest: nothing of the user stays in the memory of the
 * page (the local stores, the cache of queries, the editor saving to the server); a seam for
 * tests. */
export const afterLogout = { reload: () => window.location.reload() };

/** Ends the session of this browser, or every session of the user. */
export async function logout(everywhere = false): Promise<void> {
  const { error } = await api.POST(everywhere ? "/api/v1/auth/logout-all" : "/api/v1/auth/logout");
  if (error !== undefined) throw error;
}

/** Asks for a letter with a login link (FR-AUTH-05); 202 whether or not the address has an
 * account. */
export async function requestLoginLink(body: Schemas["EmailLoginRequest"]): Promise<void> {
  const { error } = await api.POST("/api/v1/auth/email/request", { body });
  if (error !== undefined) throw error;
}

/** Signs in with the token of a login link; the response sets the session cookie. */
export async function verifyLoginLink(token: string): Promise<Schemas["EmailLogin"]> {
  const { data, error } = await api.POST("/api/v1/auth/email/verify", { body: { token } });
  if (error !== undefined) throw error;
  return data;
}
