// Response bodies of the mocks, typed by the API schema: a contract change breaks them at compile time.
import type { Schemas } from "@/lib/api/client";

export const config: Schemas["ConfigResponse"] = {
  version: "0.1.0",
  features: { captcha: false, formal_stage: false, industrial_mode: false, reports: false },
  difficulties: [
    { key: "easy", title: "Easy", token: "e" },
    { key: "medium", title: "Medium", token: "m" },
    { key: "hard", title: "Hard", token: "h" },
  ],
  limits: {
    solution: { max_bytes: 65536, max_lines: 2000 },
    quotas: {
      guest: { checks_per_hour: 10, concurrent: 1, heavy_per_day: 0, waveforms_per_hour: 5 },
      user: { checks_per_hour: 60, concurrent: 2, heavy_per_day: 20, waveforms_per_hour: 20 },
    },
  },
  auth_providers: [],
};
