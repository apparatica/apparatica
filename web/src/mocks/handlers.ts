// MSW handlers of the API for tests (and, from T1.0, for development without the backend).
// The scenarios of every phase come with its contract PR (specs/05 §0).
import { http, HttpResponse } from "msw";

import * as fixtures from "./fixtures";

/** Matches the path on any origin: the client may use a relative or an absolute base URL. */
export const api = (path: `/api/v1/${string}`) => `*${path}`;

export const handlers = [http.get(api("/api/v1/config"), () => HttpResponse.json(fixtures.config))];
