// The API as the browser sees it: on the origin of the site (docs/api.md). Mutating requests carry
// the CSRF token (./csrf.ts). A request that gets no response marks the connection lost
// (src/lib/connectivity.ts).
import { reportNetworkError } from "@/lib/connectivity";

import { createApiClient } from "./client";
import { withCsrf } from "./csrf";

const origin = globalThis.location?.origin ?? "";

export const browserApi = createApiClient({
  baseUrl: origin,
  fetch: withCsrf((request) =>
    globalThis.fetch(request).catch((error: unknown) => {
      reportNetworkError(error);
      throw error;
    }),
  ),
});

/** An absolute URL of the API, for requests outside the client (event streams). */
export const apiUrl = (path: `/api/v1/${string}`) => `${origin}${path}`;
