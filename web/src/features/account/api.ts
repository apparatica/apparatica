// Requests of the own account (docs/api.md#пользователи-и-вход-ф2-контракт): who is signed in, the
// nick and the name, logout.
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

/** Ends the session of this browser, or every session of the user. */
export async function logout(everywhere = false): Promise<void> {
  const { error } = await api.POST(everywhere ? "/api/v1/auth/logout-all" : "/api/v1/auth/logout");
  if (error !== undefined) throw error;
}
