// Tests of a signed-in user of the mock API. In Node, MSW reads cookies only from the Cookie
// header, while a browser sends the cookies of its origin with a request and keeps the ones a
// response sets: the stub of fetch does the same with document.cookie.
import { vi } from "vitest";

import { SESSION_COOKIE } from "@/lib/session";
import { mockSession } from "@/mocks/users";

export function signIn(nick = "ada"): void {
  document.cookie = `${SESSION_COOKIE}=${mockSession(nick)}; Path=/`;
  const fetch = globalThis.fetch;
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const own = new URL(request.url).origin === location.origin;
    if (own) request.headers.set("cookie", document.cookie);
    const response = await fetch(request);
    if (own) for (const cookie of response.headers.getSetCookie()) document.cookie = cookie;
    return response;
  });
}

/** Ends the session of signIn(); call it after each test. */
export function signOut(): void {
  document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0`;
  vi.unstubAllGlobals();
}
