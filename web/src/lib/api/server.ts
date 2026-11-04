// The API as the Next.js server sees it (docs/api.md): `API_URL` inside the deployment, the API
// process on this machine in development. In the mock mode the mocks of the server answer.
import type { Client } from "openapi-fetch";

import { SESSION_COOKIE } from "@/lib/session";

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
