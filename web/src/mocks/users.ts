// Login, the own account and profiles of the mock API (docs/frontend.md#моки-для-разработки). The
// session is the cookie `ap_session=mock.<user id>`, readable by scripts unlike the real one. Users
// live in memory: `ada` (ada@example.com) has solved and attempted problems; a login link to
// another address creates a user, as the first login does. The id of `ada` is fixed, so her
// session outlives a reload of the page and is known to the mocks of the server too. A login link
// of the mock is printed to the console; any token works, one with `expired` in it is
// LOGIN_LINK_INVALID. CSRF is not checked.
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import * as fixtures from "./fixtures";
import { api, problem } from "./http";
import versions from "./problem-versions.json";
import { mockSubmissions } from "./submissions";

type Me = Schemas["Me"];
type ProblemStatus = NonNullable<Schemas["ProblemListItem"]["status"]>;

const SESSION = "ap_session";
const DAY_MS = 86_400_000;

interface MockUser {
  me: Me;
  statuses: Record<string, { status: ProblemStatus; solvedAt?: string }>;
  drafts: Map<string, Schemas["Draft"]>;
}

function newUser(nick: string, email: string | null, created = new Date()): MockUser {
  return {
    me: {
      id: crypto.randomUUID(),
      nick,
      display_name: null,
      avatar_url: null,
      email,
      role: "user",
      created_at: created.toISOString(),
      nick_change_available_at: null,
      delete_at: null,
    },
    statuses: {},
    drafts: new Map(),
  };
}

function seed(): Map<string, MockUser> {
  const ada = newUser("ada", "ada@example.com", new Date("2026-09-14T10:00:00Z"));
  ada.me.id = "00000000-0000-4000-8000-00000000ada0";
  ada.me.display_name = "Ada";
  ada.statuses = {
    mux4: { status: "solved", solvedAt: "2026-09-14T10:20:00Z" },
    "carry-adder": { status: "solved", solvedAt: "2026-10-02T18:05:00Z" },
    "seq-detector": { status: "attempted" },
  };
  return new Map([[ada.me.id, ada]]);
}

let users = seed();
const links = new Map<string, { email: string; next: string | null }>();

export function resetUsers(): void {
  users = seed();
  links.clear();
}

function byNick(nick: string): MockUser | undefined {
  return [...users.values()].find((user) => user.me.nick === nick);
}

/** The value of a session cookie of `nick`: tests sign in by setting it. */
export function mockSession(nick: string): string {
  const user = byNick(nick);
  if (user === undefined) throw new Error(`no mock user ${nick}`);
  return `mock.${user.me.id}`;
}

/** The signed-in user of a request, if any. */
export function mockUser(cookies: Record<string, string>): MockUser | undefined {
  const value = cookies[SESSION];
  return value?.startsWith("mock.") ? users.get(value.slice("mock.".length)) : undefined;
}

const sessionCookie = (user: MockUser) => `${SESSION}=mock.${user.me.id}; Path=/; SameSite=Lax`;
const clearedCookie = `${SESSION}=; Path=/; Max-Age=0`;

function unauthenticated() {
  return problem(401, "UNAUTHENTICATED", "Sign in first");
}

/** A nick like the API gives an email login: random, the address is not public. */
function randomNick(): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  const pick = () => alphabet[Math.floor(Math.random() * alphabet.length)];
  return `user-${Array.from({ length: 6 }, pick).join("")}`;
}

/** The user of an address, a new one with a random free nick if there is none. */
function userOf(email: string): { user: MockUser; created: boolean } {
  const found = [...users.values()].find((user) => user.me.email === email);
  if (found !== undefined) return { user: found, created: false };
  let nick = randomNick();
  while (byNick(nick) !== undefined) nick = randomNick();
  const user = newUser(nick, email);
  users.set(user.me.id, user);
  return { user, created: true };
}

const problems = () => fixtures.problems;

function profileOf(user: MockUser): Schemas["Profile"] {
  const solved = problems()
    .filter((item) => user.statuses[item.slug]?.status === "solved")
    .map(({ slug, number, title, difficulty }) => ({
      slug,
      number,
      title,
      difficulty,
      solved_at: user.statuses[slug]?.solvedAt ?? user.me.created_at,
    }))
    .sort((a, b) => b.solved_at.localeCompare(a.solved_at));
  return {
    nick: user.me.nick,
    display_name: user.me.display_name,
    avatar_url: user.me.avatar_url,
    created_at: user.me.created_at,
    progress: fixtures.config.difficulties.map(({ key }) => ({
      difficulty: key,
      solved: solved.filter((item) => item.difficulty === key).length,
      total: problems().filter((item) => item.difficulty === key).length,
    })),
    solved,
  };
}

/** The status of a problem for the user of the request, as the catalogue shows it. */
export function statusOf(user: MockUser, slug: string): ProblemStatus {
  return user.statuses[slug]?.status ?? "not_started";
}

export const userHandlers = [
  http.get(api("/api/v1/auth/:provider/login"), ({ params, request }) => {
    if (params.provider !== "github") return problem(404, "NOT_FOUND", "No such provider");
    const next = new URL(request.url).searchParams.get("next") ?? "/";
    const callback = new URL(`/api/v1/auth/github/callback`, request.url);
    callback.search = new URLSearchParams({ code: "mock", state: next }).toString();
    return new HttpResponse(null, { status: 302, headers: { Location: callback.href } });
  }),
  // The mock carries `next` in `state`; the real API keeps it on the server.
  http.get(api("/api/v1/auth/:provider/callback"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    if (params.get("error") !== null) {
      return new HttpResponse(null, {
        status: 302,
        headers: { Location: "/login?error=access_denied" },
      });
    }
    const user = byNick("ada") ?? userOf("ada@example.com").user;
    return new HttpResponse(null, {
      status: 302,
      headers: { Location: params.get("state") ?? "/", "Set-Cookie": sessionCookie(user) },
    });
  }),
  http.post(api("/api/v1/auth/email/request"), async ({ request }) => {
    const body = (await request.json()) as Schemas["EmailLoginRequest"];
    const token = `mock-${crypto.randomUUID()}`;
    links.set(token, { email: body.email.toLowerCase(), next: body.next ?? null });
    console.info(`[mock] login link for ${body.email}: /login/email/verify#token=${token}`);
    return new HttpResponse(null, { status: 202 });
  }),
  http.post(api("/api/v1/auth/email/verify"), async ({ request }) => {
    const { token } = (await request.json()) as Schemas["EmailLoginVerify"];
    const link = links.get(token) ?? { email: "ada@example.com", next: null };
    if (token.includes("expired")) {
      return problem(400, "LOGIN_LINK_INVALID", "The login link is unknown, used or expired");
    }
    links.delete(token);
    const { user, created } = userOf(link.email);
    const body: Schemas["EmailLogin"] = { user: user.me, created, next: link.next };
    return HttpResponse.json(body, { headers: { "Set-Cookie": sessionCookie(user) } });
  }),
  http.post(
    api("/api/v1/auth/logout"),
    () => new HttpResponse(null, { status: 204, headers: { "Set-Cookie": clearedCookie } }),
  ),
  http.post(api("/api/v1/auth/logout-all"), ({ cookies }) =>
    mockUser(cookies) === undefined
      ? unauthenticated()
      : new HttpResponse(null, { status: 204, headers: { "Set-Cookie": clearedCookie } }),
  ),

  http.get(api("/api/v1/me"), ({ cookies }) => {
    const user = mockUser(cookies);
    return user === undefined ? unauthenticated() : HttpResponse.json(user.me);
  }),
  http.patch(api("/api/v1/me"), async ({ cookies, request }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    const body = (await request.json()) as Schemas["MeUpdate"];
    if (body.nick != null && body.nick !== user.me.nick) {
      const available = user.me.nick_change_available_at;
      if (available !== null && Date.parse(available) > Date.now()) {
        return problem(409, "NICK_CHANGE_TOO_SOON", "The nick changes once in 30 days", {
          available_at: available,
        });
      }
      if (byNick(body.nick) !== undefined) {
        return problem(409, "NICK_TAKEN", `The nick '${body.nick}' is taken`);
      }
      user.me.nick = body.nick;
      user.me.nick_change_available_at = new Date(Date.now() + 30 * DAY_MS).toISOString();
    }
    if ("display_name" in body) user.me.display_name = body.display_name ?? null;
    return HttpResponse.json(user.me);
  }),
  http.delete(api("/api/v1/me"), ({ cookies }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    user.me.delete_at ??= new Date(Date.now() + 7 * DAY_MS).toISOString();
    return HttpResponse.json(user.me, { status: 202 });
  }),
  http.post(api("/api/v1/me/restore"), ({ cookies }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    user.me.delete_at = null;
    return HttpResponse.json(user.me);
  }),
  http.get(api("/api/v1/me/export"), ({ cookies }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    const body: Schemas["AccountExport"] = {
      format: "apparatica-export/1",
      exported_at: new Date().toISOString(),
      user: user.me,
      identities: [{ provider: "email", email: user.me.email, created_at: user.me.created_at }],
      consents: [
        { document: "terms", version: "2026-11-03", accepted_at: user.me.created_at },
        { document: "privacy", version: "2026-11-03", accepted_at: user.me.created_at },
      ],
      submissions: mockSubmissions().map((submission) => ({
        id: submission.id,
        problem: submission.problem,
        problem_title: submission.problem_title,
        version: submission.version,
        kind: submission.kind,
        status: submission.status,
        verdict_detail: submission.verdict_detail,
        created_at: submission.created_at,
        finished_at: submission.finished_at,
        code: submission.code,
        seed: submission.seed,
        toolchain_profile: submission.toolchain_profile,
      })),
      drafts: [...user.drafts].map(([slug, draft]) => ({ ...draft, problem: slug })),
    };
    const name = `apparatica-${user.me.nick}.json`;
    return HttpResponse.json(body, {
      headers: { "Content-Disposition": `attachment; filename="${name}"` },
    });
  }),
  http.get(api("/api/v1/me/drafts/:slug"), ({ cookies, params }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    const draft = user.drafts.get(String(params.slug));
    return draft === undefined
      ? problem(404, "NOT_FOUND", `No draft of '${String(params.slug)}'`)
      : HttpResponse.json(draft);
  }),
  http.put(api("/api/v1/me/drafts/:slug"), async ({ cookies, params, request }) => {
    const user = mockUser(cookies);
    if (user === undefined) return unauthenticated();
    const slug = String(params.slug);
    if (!versions.some((version) => version.slug === slug)) {
      return problem(404, "NOT_FOUND", `No published problem '${slug}'`);
    }
    const body = (await request.json()) as Schemas["DraftSave"];
    const limit = fixtures.config.limits.solution.max_bytes;
    if (new TextEncoder().encode(body.code).length > limit) {
      return problem(413, "CODE_TOO_LARGE", `The code is over ${limit} bytes`, { limit });
    }
    const draft: Schemas["Draft"] = { ...body, updated_at: new Date().toISOString() };
    user.drafts.set(slug, draft);
    return HttpResponse.json(draft);
  }),
  http.get(api("/api/v1/users/:nick"), ({ params }) => {
    const user = byNick(String(params.nick));
    return user === undefined || user.me.delete_at !== null
      ? problem(404, "NOT_FOUND", `No user '${String(params.nick)}'`)
      : HttpResponse.json(profileOf(user));
  }),
];
