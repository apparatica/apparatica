// The API as the Next.js server sees it (docs/api.md): `API_URL` inside the deployment, the API
// process on this machine in development. In the mock mode the mocks of the server answer.
import type { Client } from "openapi-fetch";

import { GUEST_COOKIE, SESSION_COOKIE } from "@/lib/session";

import { createApiClient, type paths } from "./client";

const baseUrl = process.env.API_URL ?? "http://localhost:8000";

export const serverApi = createApiClient({ baseUrl });

/** The API as the user of a request sees it: `session` (the value of the session cookie of the
 * browser) goes with the requests, and no other cookie. Without it, the API of a guest. The
 * answers are the user's own: they are not shared between requests. */
export function sessionApi(session: string | null | undefined): Client<paths> {
  if (session == null) return serverApi;
  return createApiClient({
    baseUrl,
    headers: { Cookie: `${SESSION_COOKIE}=${session}` },
    cache: "no-store",
  });
}

/** The cookies of the API in a request of the browser: who the visitor is. */
export interface Visitor {
  /** The value of the session cookie. */
  session: string | null;
  /** The value of the guest cookie: what a guest may see depends on their own Submits. */
  guest: string | null;
}

/** The API as the visitor of a request sees it, a signed-in user or a guest (the code of others
 * opens after an own accepted Submit, FR-SOL-02). The answers are the visitor's own. */
export function visitorApi({ session, guest }: Visitor): Client<paths> {
  const cookies = [
    session === null ? null : `${SESSION_COOKIE}=${session}`,
    guest === null ? null : `${GUEST_COOKIE}=${guest}`,
  ].filter((cookie) => cookie !== null);
  if (cookies.length === 0) return serverApi;
  return createApiClient({ baseUrl, headers: { Cookie: cookies.join("; ") }, cache: "no-store" });
}

/** The visitor of the request being rendered, from its cookies. */
export function visitorOf(jar: { get: (name: string) => { value: string } | undefined }): Visitor {
  return {
    session: jar.get(SESSION_COOKIE)?.value ?? null,
    guest: jar.get(GUEST_COOKIE)?.value ?? null,
  };
}
