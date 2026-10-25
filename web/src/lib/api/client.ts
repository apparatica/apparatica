// Typed client of the Apparatica API (docs/api.md). The types are generated from
// backend/openapi.json by `just openapi`; do not edit schema.d.ts by hand.
import createClient, { type Client, type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];
/** An error response, `application/problem+json` (specs/05 §2). */
export type ApiError = Schemas["Error"];
export type ErrorCode = Schemas["ErrorCode"];

/** Paths of the schema start with /api/v1, so `baseUrl` is the origin of the API (empty: the
 * same origin as the site). `fetch` is looked up at each call, not when the client is created,
 * so that a fetch patched later (Next.js caching, MSW in tests) is the one used. */
export function createApiClient(options: ClientOptions = {}): Client<paths> {
  return createClient<paths>({ fetch: (request) => globalThis.fetch(request), ...options });
}
