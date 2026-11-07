// Leaderboards, public solutions and reference solutions of the mock API (phase 3). Every demo
// problem ranks by its synthesis metrics, delay then area, as its package says; the reference gets
// a made-up measurement, not the one of the toolchain (T3.3). The rivals are a fixed,
// seeded crowd without accounts: every problem has some, with shared places and solutions that
// match the reference syntax tree (grouped under the earliest). Signed-in users of users.ts join
// with the seeded solutions of `ada` and with their accepted Submits (submissions.ts), measured
// from a hash of the code; the reference code itself measures as the reference. A guest or a user
// without an accepted Submit of the problem sees no code of others and no reference.
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api, problem as apiProblem } from "./http";
import versions from "./problem-versions.json";
import referenceFile from "./reference-solutions.json";
import { mockSubmissions, publicChecks } from "./submissions";
import { ADA_ID, type MockUser, mockAccounts, mockUser, statusOf } from "./users";

type Metrics = Record<string, number>;
type UserRef = Schemas["UserRef"];
type Row = Schemas["LeaderboardRow"];

/** The reference solutions of the packages (scripts/mock_problems.py), without metrics. */
export const references = referenceFile as Record<
  string,
  Omit<Schemas["ReferenceSolution"], "metrics">[] | undefined
>;

/** The formula of every demo package (problems/): delay, then area. */
export const MOCK_FORMULA: Schemas["LeaderboardFormula"] = {
  formula_version: 1,
  order: [
    { metric: "synth.critical_path_ns", dir: "asc" },
    { metric: "synth.area_um2", dir: "asc" },
  ],
};
const COLUMNS = ["synth.critical_path_ns", "synth.area_um2", "synth.cells", "synth.flops"];
const PROFILE = "sv-2026.10.2";
const GROUP_LIMIT = 50;
const POINTS: Record<string, number> = { easy: 1, medium: 3, hard: 6 };
const BONUS = [3, 2, 1];
const DAY_MS = 86_400_000;
const SEASON = Date.parse("2026-09-01T00:00:00Z");

interface Measure {
  delay: number;
  area: number;
  cells: number;
  flops: number;
  depth: number;
}

/** The made-up synthesis of the reference solution of every demo problem. */
const REFERENCE: Record<string, Measure> = {
  mux4: { delay: 0.12, area: 52.4, cells: 24, flops: 0, depth: 3 },
  "counter-mod-n": { delay: 0.38, area: 118.2, cells: 41, flops: 4, depth: 7 },
  "carry-adder": { delay: 0.61, area: 96.8, cells: 38, flops: 0, depth: 12 },
  "seq-detector": { delay: 0.29, area: 61.4, cells: 19, flops: 3, depth: 5 },
  "sync-fifo": { delay: 0.91, area: 902, cells: 201, flops: 140, depth: 14 },
};
/** Rivals with a solution of each problem. */
const CROWD: Record<string, number> = {
  mux4: 140,
  "counter-mod-n": 96,
  "carry-adder": 75,
  "seq-detector": 41,
  "sync-fifo": 304,
};
/** The seeded solved problems of `ada` (users.ts) are public solutions too. */
const ADA_SOLVED = [
  { slug: "mux4", at: "2026-09-14T10:20:00Z" },
  { slug: "carry-adder", at: "2026-10-02T18:05:00Z" },
];

type Author = { kind: "rival"; nick: string } | { kind: "account"; user: MockUser };

interface Solution {
  id: string;
  slug: string;
  author: Author;
  /** Same value, same normalized syntax tree. */
  ast: string;
  metrics: Metrics;
  depth: number;
  submittedAt: string;
  code: string;
  status: "accepted" | "accepted_with_warnings";
}

interface Entry {
  solution: Solution;
  rank: number;
  /** The earlier solution with the same syntax tree, which holds the place. */
  leader: Solution | null;
  followers: Solution[];
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** A seeded generator of numbers in [0, 1) (mulberry32). */
function random(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (value: number, digits: number) => Number(value.toFixed(digits));
const uuid = (problem: number, index: number) =>
  `0193a000-0000-7000-8${problem.toString(16).padStart(3, "0")}-${index.toString(16).padStart(12, "0")}`;

function measure(slug: string, next: () => number): Measure {
  const base = REFERENCE[slug] ?? { delay: 1, area: 100, cells: 50, flops: 0, depth: 8 };
  return {
    delay: round(base.delay * (0.78 + 0.6 * next()), 2),
    area: round(base.area * (0.8 + 0.5 * next()), 1),
    cells: Math.round(base.cells * (0.8 + 0.5 * next())),
    flops: base.flops + Math.floor(next() * 3),
    depth: Math.max(1, base.depth + Math.floor(next() * 5) - 2),
  };
}

const metricsOf = (m: Measure): Metrics => ({
  "synth.critical_path_ns": m.delay,
  "synth.area_um2": m.area,
  "synth.cells": m.cells,
  "synth.flops": m.flops,
});

const referenceCode = (slug: string) => references[slug]?.[0]?.code ?? "";
const normalized = (code: string) => code.replace(/\/\/.*$/gm, "").replace(/\s+/g, "");

const NICK_HEADS = ["rtl", "fpga", "asic", "clk", "lut", "flop", "mux", "gate", "wire", "bus"];
const NICK_TAILS = ["fan", "owl", "fox", "lynx", "bee", "elk", "yak", "koi", "wren", "hawk"];
const nickOf = (index: number) => {
  const head = NICK_HEADS[index % NICK_HEADS.length] ?? "rtl";
  const tail = NICK_TAILS[Math.floor(index / NICK_HEADS.length) % NICK_TAILS.length] ?? "fan";
  const lap = Math.floor(index / (NICK_HEADS.length * NICK_TAILS.length));
  return lap === 0 ? `${head}_${tail}` : `${head}_${tail}${lap + 1}`;
};

/** The rivals of every problem, seeded by its number. */
const rivals: Solution[] = fixtures.problems.flatMap(({ slug, number }) => {
  const next = random(number * 7919);
  const reference = REFERENCE[slug];
  const code = referenceCode(slug);
  const solutions: Solution[] = [];
  for (let i = 0; i < (CROWD[slug] ?? 0); i += 1) {
    const nick = nickOf((i * 37 + number * 11) % 320);
    const asReference = i % 9 === 4 && reference !== undefined;
    let m = asReference ? reference : measure(slug, next);
    const previous = solutions.at(-1);
    if (i % 13 === 7 && previous !== undefined) {
      // A different solution with the same metrics: a shared place.
      m = { ...m, delay: previous.metrics["synth.critical_path_ns"] ?? m.delay };
      m.area = previous.metrics["synth.area_um2"] ?? m.area;
    }
    solutions.push({
      id: uuid(number, i + 1),
      slug,
      author: { kind: "rival", nick },
      ast: asReference ? "reference" : `rival-${i}`,
      metrics: metricsOf(m),
      depth: m.depth,
      submittedAt: new Date(SEASON + Math.floor(next() * 60 * DAY_MS)).toISOString(),
      code: asReference ? code : `// ${nick}\n${code}`,
      status: i % 6 === 5 ? "accepted_with_warnings" : "accepted",
    });
  }
  return solutions;
});

function accountSolution(
  user: MockUser,
  slug: string,
  id: string,
  code: string,
  submittedAt: string,
): Solution {
  const asReference = normalized(code) === normalized(referenceCode(slug));
  const reference = REFERENCE[slug];
  const m = asReference && reference !== undefined ? reference : measure(slug, random(hash(code)));
  return {
    id,
    slug,
    author: { kind: "account", user },
    ast: asReference ? "reference" : `code-${hash(normalized(code))}`,
    metrics: metricsOf(m),
    depth: m.depth,
    submittedAt,
    code,
    status: "accepted",
  };
}

/** Public solutions: the rivals, the seeded ones of `ada`, the accepted Submits of users. */
function solutions(slug?: string): Solution[] {
  const accounts = new Map(
    mockAccounts()
      .filter((user) => user.me.delete_at === null)
      .map((user) => [user.me.id, user]),
  );
  const ada = accounts.get(ADA_ID);
  const seeded =
    ada === undefined
      ? []
      : ADA_SOLVED.map(({ slug: problem, at }, index) =>
          accountSolution(
            ada,
            problem,
            uuid(0xada, index + 1),
            `// ada\n${referenceCode(problem).replace("module", "module /* mine */")}`,
            at,
          ),
        );
  const checks = publicChecks().flatMap((check) => {
    const user = accounts.get(check.author);
    return user === undefined
      ? []
      : [accountSolution(user, check.problem, check.id, check.code, check.created)];
  });
  return [...rivals, ...seeded, ...checks].filter(
    (item) => slug === undefined || item.slug === slug,
  );
}

const authorKey = (author: Author) =>
  author.kind === "rival" ? `rival:${author.nick}` : `user:${author.user.me.id}`;

function authorRef(author: Author): UserRef {
  return author.kind === "rival"
    ? { nick: author.nick, display_name: null, avatar_url: null }
    : {
        nick: author.user.me.nick,
        display_name: author.user.me.display_name,
        avatar_url: author.user.me.avatar_url,
      };
}

const sortValues = (item: Solution) =>
  MOCK_FORMULA.order.map(
    ({ metric, dir }) => (item.metrics[metric] ?? 0) * (dir === "asc" ? 1 : -1),
  );

function compareValues(a: Solution, b: Solution): number {
  const [x, y] = [sortValues(a), sortValues(b)];
  for (let i = 0; i < x.length; i += 1) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

const byFormula = (a: Solution, b: Solution) =>
  compareValues(a, b) || a.submittedAt.localeCompare(b.submittedAt);

/** The entries of a problem in the order of the leaderboard, each leader before its followers. */
function board(slug: string): Entry[] {
  const best = new Map<string, Solution>();
  for (const item of solutions(slug)) {
    const key = authorKey(item.author);
    const kept = best.get(key);
    if (kept === undefined || byFormula(item, kept) < 0) best.set(key, item);
  }
  const sorted = [...best.values()].sort(byFormula);
  const leaders = new Map<string, Solution>();
  for (const item of [...sorted].sort((a, b) => a.submittedAt.localeCompare(b.submittedAt))) {
    if (!leaders.has(item.ast)) leaders.set(item.ast, item);
  }
  const heads = sorted.filter((item) => leaders.get(item.ast) === item);
  const entries: Entry[] = [];
  for (const head of heads) {
    const rank = 1 + heads.filter((other) => compareValues(other, head) < 0).length;
    const followers = sorted
      .filter((item) => item.ast === head.ast && item !== head)
      .sort((a, b) => a.submittedAt.localeCompare(b.submittedAt));
    entries.push({ solution: head, rank, leader: null, followers });
    for (const follower of followers) {
      entries.push({ solution: follower, rank, leader: head, followers: [] });
    }
  }
  return entries;
}

function placement(entries: Entry[], entry: Entry, solutionId: string) {
  const others = Math.max(1, entries.length - 1);
  return {
    rank: entry.rank,
    total: entries.length,
    better_than: round(entries.filter((other) => other.rank > entry.rank).length / others, 4),
    is_best: entry.solution.id === solutionId,
    duplicate_of: entry.leader?.id ?? null,
  };
}

/** The place of the author of an accepted Submit (submissions.ts): null outside a leaderboard. */
export function mockPlacement(
  slug: string,
  solutionId: string,
): Schemas["LeaderboardPlacement"] | null {
  const entries = board(slug);
  const own = solutions(slug).find((item) => item.id === solutionId);
  if (own === undefined) return null;
  const entry = entries.find((item) => authorKey(item.solution.author) === authorKey(own.author));
  return entry === undefined ? null : placement(entries, entry, solutionId);
}

const duplicateOf = (leader: Solution | null) =>
  leader === null ? null : { solution_id: leader.id, author: authorRef(leader.author) };

function row(entry: Entry, group: boolean, me: string | null): Row {
  const { solution } = entry;
  return {
    rank: entry.rank,
    solution_id: solution.id,
    author: authorRef(solution.author),
    metrics: solution.metrics,
    submitted_at: solution.submittedAt,
    is_me: authorKey(solution.author) === me,
    duplicate_of: duplicateOf(entry.leader),
    duplicates: group ? entry.followers.length : 0,
    group: group
      ? entry.followers.slice(0, GROUP_LIMIT).map((item) => ({
          solution_id: item.id,
          author: authorRef(item.author),
          submitted_at: item.submittedAt,
        }))
      : [],
  };
}

const SORT = /^(rank|-?submitted_at|-?[a-z_]+\.[a-z0-9_]+)$/;

/** A comparator of `sort`, or null for a metric that is not a column. */
function sorter<T>(
  sort: string,
  of: (item: T) => Solution,
  place: (item: T) => number,
): ((a: T, b: T) => number) | null {
  if (!SORT.test(sort)) return null;
  const key = sort.replace(/^-/, "");
  const direction = sort.startsWith("-") ? -1 : 1;
  if (key === "rank") return (a, b) => place(a) - place(b);
  if (key === "submitted_at") {
    return (a, b) => of(a).submittedAt.localeCompare(of(b).submittedAt) * direction;
  }
  if (!COLUMNS.includes(key)) return null;
  return (a, b) => ((of(a).metrics[key] ?? 0) - (of(b).metrics[key] ?? 0)) * direction;
}

function invalid(detail: string) {
  return apiProblem(422, "VALIDATION_ERROR", detail);
}

function pageOf(params: URLSearchParams): { page: number; perPage: number } | null {
  const page = Number(params.get("page") ?? 1);
  const perPage = Number(params.get("per_page") ?? 20);
  if (!Number.isInteger(page) || page < 1) return null;
  if (!Number.isInteger(perPage) || perPage < 1 || perPage > 100) return null;
  return { page, perPage };
}

/** A backend test validates the file against the API schema, which makes the cast safe. */
const versionOf = (slug: string) =>
  (versions as Schemas["ProblemVersionDetail"][]).find((item) => item.slug === slug);
const problemRef = (slug: string): Schemas["ProblemRef"] => {
  const item = fixtures.problems.find((problem) => problem.slug === slug);
  return {
    slug,
    number: item?.number ?? 0,
    title: item?.title ?? slug,
    difficulty: item?.difficulty ?? "easy",
  };
};

/** Whether the visitor has an accepted Submit of the problem: the code of others opens. */
function solvedBy(cookies: Record<string, string>, slug: string): boolean {
  const user = mockUser(cookies);
  if (user !== undefined) return statusOf(user, slug) === "solved";
  return mockSubmissions().some(
    (item) =>
      item.problem === slug &&
      item.kind === "submit" &&
      (item.status === "accepted" || item.status === "accepted_with_warnings"),
  );
}

const visitorKey = (cookies: Record<string, string>) => {
  const user = mockUser(cookies);
  return user === undefined ? null : `user:${user.me.id}`;
};

function summary(item: Solution, entries: Entry[]): Schemas["SolutionSummary"] {
  const entry = entries.find((candidate) => candidate.solution.id === item.id);
  return {
    id: item.id,
    problem: problemRef(item.slug),
    version: versionOf(item.slug)?.version ?? 1,
    author: authorRef(item.author),
    status: item.status,
    metrics: item.metrics,
    rank: entry?.rank ?? null,
    duplicate_of: duplicateOf(entry?.leader ?? null),
    submitted_at: item.submittedAt,
  };
}

function stagesOf(item: Solution): Schemas["PublicStage"][] {
  const version = versionOf(item.slug);
  const total = Object.values(version?.tests ?? {}).reduce((sum, count) => sum + count, 0);
  const delay = item.metrics["synth.critical_path_ns"] ?? 1;
  const synth = {
    critical_path_ns: delay,
    fmax_mhz: round(1000 / delay, 1),
    area_um2: item.metrics["synth.area_um2"] ?? 0,
    cells: item.metrics["synth.cells"] ?? 0,
    flops: item.metrics["synth.flops"] ?? 0,
    latches: 0,
    logic_depth: item.depth,
    liberty: "nangate45",
  };
  const stages: Schemas["PublicStage"][] = (version?.pipeline.submit ?? []).map(
    ({ key, type }) => ({
      key,
      type,
      status: type === "lint" && item.status === "accepted_with_warnings" ? "warning" : "passed",
      metrics_schema: `${type}/v1`,
      metrics: type === "synth" ? synth : {},
      tests: type === "sim" ? { passed: total, total } : null,
    }),
  );
  // A package without synthesis still ranks by the made-up one.
  if (!stages.some((stage) => stage.type === "synth")) {
    stages.push({
      key: "synth",
      type: "synth",
      status: "passed",
      metrics_schema: "synth/v1",
      metrics: synth,
      tests: null,
    });
  }
  return stages;
}

const referenceMetrics = (slug: string): Metrics | null => {
  const reference = REFERENCE[slug];
  return reference === undefined ? null : metricsOf(reference);
};

interface Rating {
  key: string;
  user: UserRef;
  points: number;
  solved: Record<string, number>;
  reached: string;
  week: number | null;
}

/** Everyone with points, by points, then whoever reached them first. */
function ratings(): Rating[] {
  const all = new Map<string, Rating>();
  const counted = new Set<string>();
  for (const item of solutions()) {
    const key = authorKey(item.author);
    const rating = all.get(key) ?? {
      key,
      user: authorRef(item.author),
      points: 0,
      solved: Object.fromEntries(fixtures.config.difficulties.map(({ key: level }) => [level, 0])),
      reached: item.submittedAt,
      week: null,
    };
    if (!counted.has(`${key} ${item.slug}`)) {
      counted.add(`${key} ${item.slug}`);
      const level = problemRef(item.slug).difficulty;
      rating.solved[level] = (rating.solved[level] ?? 0) + 1;
      rating.points += POINTS[level] ?? 0;
    }
    if (item.submittedAt > rating.reached) rating.reached = item.submittedAt;
    all.set(key, rating);
  }
  for (const { slug } of fixtures.problems) {
    for (const entry of board(slug)) {
      const bonus = entry.leader === null ? (BONUS[entry.rank - 1] ?? 0) : 0;
      const rating = all.get(authorKey(entry.solution.author));
      if (rating !== undefined) rating.points += bonus;
    }
  }
  return [...all.values()]
    .map((rating) => {
      const next = random(hash(rating.key));
      const week = next() < 0.2 ? null : Math.round((next() - 0.4) * 8);
      return { ...rating, week };
    })
    .filter((rating) => rating.points > 0)
    .sort((a, b) => b.points - a.points || a.reached.localeCompare(b.reached));
}

const ratingRow = (rating: Rating, rank: number, me: string | null): Schemas["RatingRow"] => ({
  rank,
  user: rating.user,
  points: rating.points,
  solved: rating.solved,
  week_delta: rating.week,
  is_me: rating.key === me,
});

const keyOfNick = (nick: string): string | null => {
  const account = mockAccounts().find((user) => user.me.nick === nick);
  if (account !== undefined) return account.me.delete_at === null ? `user:${account.me.id}` : null;
  return rivals.some((item) => item.author.kind === "rival" && item.author.nick === nick)
    ? `rival:${nick}`
    : null;
};

/** The places, best places and public solutions of a profile (users.ts). */
export function mockStanding(
  nick: string,
): Pick<Schemas["Profile"], "rating" | "best_places" | "solutions"> {
  const key = keyOfNick(nick);
  const all = ratings();
  const index = all.findIndex((rating) => rating.key === key);
  const own = solutions().filter((item) => authorKey(item.author) === key);
  const places = fixtures.problems.flatMap(({ slug }) => {
    const entries = board(slug);
    const entry = entries.find((item) => authorKey(item.solution.author) === key);
    return entry === undefined
      ? []
      : [
          {
            problem: problemRef(slug),
            rank: entry.rank,
            entries: entries.length,
            solution_id: entry.solution.id,
          },
        ];
  });
  return {
    rating:
      index < 0 ? null : { rank: index + 1, total: all.length, points: all[index]?.points ?? 0 },
    best_places: places
      .sort((a, b) => a.rank - b.rank || a.problem.number - b.problem.number)
      .slice(0, 10),
    solutions: own.length,
  };
}

/** The profile of a rival, who has no account (users.ts asks after its own users). */
export function rivalProfile(nick: string): Schemas["Profile"] | null {
  const own = rivals.filter((item) => item.author.kind === "rival" && item.author.nick === nick);
  if (own.length === 0) return null;
  const first = own.reduce((a, b) => (a.submittedAt < b.submittedAt ? a : b));
  const solved = own
    .map((item) => ({ ...problemRef(item.slug), solved_at: item.submittedAt }))
    .sort((a, b) => b.solved_at.localeCompare(a.solved_at));
  return {
    nick,
    display_name: null,
    avatar_url: null,
    created_at: new Date(Date.parse(first.submittedAt) - 10 * DAY_MS).toISOString(),
    progress: fixtures.config.difficulties.map(({ key }) => ({
      difficulty: key,
      solved: solved.filter((item) => item.difficulty === key).length,
      total: fixtures.problems.filter((item) => item.difficulty === key).length,
    })),
    solved,
    ...mockStanding(nick),
  };
}

function notFound(what: string) {
  return apiProblem(404, "NOT_FOUND", `No ${what}`);
}

export const leaderboardHandlers = [
  http.get(api("/api/v1/problems/:slug/leaderboard"), ({ cookies, params, request }) => {
    const slug = String(params.slug);
    if (versionOf(slug) === undefined) return notFound(`published problem '${slug}'`);
    const query = new URL(request.url).searchParams;
    const paging = pageOf(query);
    const group = query.get("group") !== "false";
    const around = query.get("around");
    if (paging === null || (around !== null && around !== "me")) return invalid("Bad paging");
    const entries = board(slug);
    const rows = group ? entries.filter((entry) => entry.leader === null) : entries;
    const compare = sorter<Entry>(
      query.get("sort") ?? "rank",
      (entry) => entry.solution,
      (entry) => entries.indexOf(entry),
    );
    if (compare === null) return invalid("`sort` names no column");
    const sorted = [...rows].sort(
      (a, b) => compare(a, b) || entries.indexOf(a) - entries.indexOf(b),
    );
    const me = visitorKey(cookies);
    const mine = entries.find((entry) => authorKey(entry.solution.author) === me);
    let { page } = paging;
    if (around === "me" && mine !== undefined) {
      const shown =
        group && mine.leader !== null ? entries.find((e) => e.solution === mine.leader) : mine;
      const index = sorted.findIndex((entry) => entry === shown);
      if (index >= 0) page = Math.floor(index / paging.perPage) + 1;
    }
    const first = entries[0];
    const reference = referenceMetrics(slug);
    const body: Schemas["ProblemLeaderboard"] = {
      items: sorted
        .slice((page - 1) * paging.perPage, page * paging.perPage)
        .map((entry) => row(entry, group, me)),
      page,
      per_page: paging.perPage,
      total: sorted.length,
      entries: entries.length,
      epoch: 1,
      toolchain_profile: PROFILE,
      formula_version: MOCK_FORMULA.formula_version,
      order: MOCK_FORMULA.order,
      columns: COLUMNS,
      best: first === undefined ? null : row(first, group, me),
      reference:
        reference === null
          ? null
          : {
              title: references[slug]?.[0]?.title ?? "",
              metrics: reference,
            },
      me: mine === undefined ? null : row(mine, group, me),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/problems/:slug/solutions"), ({ cookies, params, request }) => {
    const slug = String(params.slug);
    if (versionOf(slug) === undefined) return notFound(`published problem '${slug}'`);
    const query = new URL(request.url).searchParams;
    const paging = pageOf(query);
    if (paging === null) return invalid("Bad paging");
    const entries = board(slug);
    const all = solutions(slug).sort(byFormula);
    const compare = sorter<Solution>(
      query.get("sort") ?? "rank",
      (item) => item,
      (item) => all.indexOf(item),
    );
    if (compare === null) return invalid("`sort` names no column");
    const sorted = [...all].sort((a, b) => compare(a, b) || all.indexOf(a) - all.indexOf(b));
    const { page, perPage } = paging;
    const body: Schemas["SolutionPage"] = {
      items: sorted
        .slice((page - 1) * perPage, page * perPage)
        .map((item) => summary(item, entries)),
      page,
      per_page: perPage,
      total: sorted.length,
      code_locked: !solvedBy(cookies, slug),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/problems/:slug/reference"), ({ cookies, params }) => {
    const slug = String(params.slug);
    const version = versionOf(slug);
    if (version?.reference == null) return notFound(`reference solutions of '${slug}'`);
    const { visibility } = version.reference;
    if (visibility === "after_accepted" && !solvedBy(cookies, slug)) {
      return apiProblem(403, "REFERENCE_LOCKED", "The reference opens after your accepted Submit");
    }
    const listed = references[slug] ?? [];
    const body: Schemas["ReferencePage"] = {
      version: version.version,
      visibility,
      solutions: listed.map((item, index) => ({
        ...item,
        metrics: index === 0 ? referenceMetrics(slug) : null,
      })),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/solutions/:id"), ({ cookies, params }) => {
    const id = String(params.id);
    const item = solutions().find((candidate) => candidate.id === id);
    if (item === undefined) return notFound(`public solution ${id}`);
    const entries = board(item.slug);
    const entry = entries.find((candidate) => candidate.solution.id === item.id);
    const own = authorKey(item.author) === visitorKey(cookies);
    const locked = !own && !solvedBy(cookies, item.slug);
    const author = authorRef(item.author);
    const profile = item.author.kind === "rival" ? rivalProfile(item.author.nick) : null;
    const created =
      item.author.kind === "account"
        ? item.author.user.me.created_at
        : (profile?.created_at ?? item.submittedAt);
    const solvedCount = new Set(
      solutions()
        .filter((candidate) => authorKey(candidate.author) === authorKey(item.author))
        .map((candidate) => candidate.slug),
    ).size;
    const body: Schemas["Solution"] = {
      ...summary(item, entries),
      author: { ...author, created_at: created, solved: solvedCount },
      language: "systemverilog",
      toolchain_profile: PROFILE,
      code: locked ? null : item.code,
      code_locked: locked,
      stages: stagesOf(item),
      placement: entry === undefined ? null : placement(entries, entry, item.id),
      order: MOCK_FORMULA.order,
      best: entries[0]?.solution.metrics ?? null,
      reference: referenceMetrics(item.slug),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/leaderboard"), ({ cookies, request }) => {
    const paging = pageOf(new URL(request.url).searchParams);
    if (paging === null) return invalid("Bad paging");
    const { page, perPage } = paging;
    const me = visitorKey(cookies);
    const all = ratings();
    const rows = all.map((rating, index) => ratingRow(rating, index + 1, me));
    const index = rows.findIndex((item) => item.is_me);
    const from = (page - 1) * perPage;
    const onPage = index >= from && index < from + perPage;
    const body: Schemas["GlobalLeaderboard"] = {
      items: rows.slice(from, from + perPage),
      page,
      per_page: perPage,
      total: rows.length,
      formula_version: 1,
      me: rows[index] ?? null,
      around_me: index < 0 || onPage ? [] : rows.slice(Math.max(0, index - 2), index + 3),
    };
    return HttpResponse.json(body);
  }),
  http.get(api("/api/v1/users/:nick/solutions"), ({ params, request }) => {
    const nick = String(params.nick);
    const key = keyOfNick(nick);
    const paging = pageOf(new URL(request.url).searchParams);
    if (paging === null) return invalid("Bad paging");
    if (key === null) return notFound(`user '${nick}'`);
    const own = solutions()
      .filter((item) => authorKey(item.author) === key)
      .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
    const { page, perPage } = paging;
    const body: Schemas["UserSolutionPage"] = {
      items: own
        .slice((page - 1) * perPage, page * perPage)
        .map((item) => summary(item, board(item.slug))),
      page,
      per_page: perPage,
      total: own.length,
    };
    return HttpResponse.json(body);
  }),
];
