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
  catalog: { per_page: 12 },
  limits: {
    solution: { max_bytes: 65536, max_lines: 2000 },
    quotas: {
      guest: { checks_per_hour: 10, concurrent: 1, heavy_per_day: 0, waveforms_per_hour: 5 },
      user: { checks_per_hour: 60, concurrent: 2, heavy_per_day: 20, waveforms_per_hour: 20 },
    },
  },
  auth_providers: [],
};

export const captchaChallenge: Schemas["CaptchaChallenge"] = {
  algorithm: "SHA-256",
  challenge: "4f1c8b7d0a2e5b9c6d3f7a1e8b4c2d9f0a5e7b3c1d8f6a2e4b9c7d0f3a5e1b8c",
  maxnumber: 50000,
  salt: "mock-salt?expires=1793000000",
  signature: "9b2e4d6f8a0c1e3b5d7f9a1c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b",
};

/** The tags of problems/tags.yaml, in its order. */
export const tags: Schemas["Tag"][] = [
  { slug: "combinational", title: "комбинационная логика" },
  { slug: "sequential", title: "последовательностная логика" },
  { slug: "arithmetic", title: "арифметика" },
  { slug: "multiplexer", title: "мультиплексоры" },
  { slug: "counter", title: "счётчики" },
  { slug: "fsm", title: "FSM" },
  { slug: "memory", title: "память" },
  { slug: "fifo", title: "FIFO" },
];

/** The demo problems of problems/, as the catalogue lists them; the acceptance rates are made up
 * (sync-fifo has no judged Submit yet). */
export const problems: Schemas["ProblemListItem"][] = [
  {
    slug: "mux4",
    number: 1,
    title: "Мультиплексор 4:1",
    difficulty: "easy",
    tags: ["combinational", "multiplexer"],
    acceptance: 0.78,
  },
  {
    slug: "counter-mod-n",
    number: 2,
    title: "Счётчик по модулю N",
    difficulty: "easy",
    tags: ["sequential", "counter"],
    acceptance: 0.71,
  },
  {
    slug: "carry-adder",
    number: 3,
    title: "Сумматор с переносом",
    difficulty: "easy",
    tags: ["combinational", "arithmetic"],
    acceptance: 0.64,
  },
  {
    slug: "seq-detector",
    number: 4,
    title: "Детектор последовательности 1011",
    difficulty: "medium",
    tags: ["sequential", "fsm"],
    acceptance: 0.52,
  },
  {
    slug: "sync-fifo",
    number: 5,
    title: "Синхронный FIFO",
    difficulty: "medium",
    tags: ["sequential", "memory", "fifo"],
    acceptance: null,
  },
];
