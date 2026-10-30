// MSW handlers of the API: tests and development without the backend (docs/frontend.md). The
// scenarios of every phase come with its contract PR (specs/05 §0).
import { http, HttpResponse } from "msw";

import { captchaHandlers } from "./captcha";
import * as fixtures from "./fixtures";
import { api } from "./http";
import { problemHandlers } from "./problems";
import { submissionHandlers } from "./submissions";

export { api };

export const handlers = [
  http.get(api("/api/v1/health"), () => HttpResponse.json(fixtures.health)),
  http.get(api("/api/v1/config"), () => HttpResponse.json(fixtures.config)),
  ...captchaHandlers,
  ...problemHandlers,
  ...submissionHandlers,
];
