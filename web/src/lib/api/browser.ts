// The API as the browser sees it: on the origin of the site (docs/api.md).
import { createApiClient } from "./client";

const origin = globalThis.location?.origin ?? "";

export const browserApi = createApiClient({ baseUrl: origin });

/** An absolute URL of the API, for requests outside the client (event streams). */
export const apiUrl = (path: `/api/v1/${string}`) => `${origin}${path}`;
