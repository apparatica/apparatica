import { describe, expect, it } from "vitest";

import { CSRF_HEADER, readCookie, withCsrf } from "./csrf";

const URL = "http://localhost/api/v1/submissions";

function refused(): Response {
  return Response.json(
    { code: "CSRF_FAILED", status: 403 },
    { status: 403, headers: { "Content-Type": "application/problem+json" } },
  );
}

/** A server that gives `responses` in turn, then 204, and records what it got. */
function server(responses: Response[]) {
  const sent: { token: string | null; body: string }[] = [];
  const send = async (request: Request) => {
    sent.push({ token: request.headers.get(CSRF_HEADER), body: await request.text() });
    return responses.shift() ?? new Response(null, { status: 204 });
  };
  return { send, sent };
}

describe("readCookie", () => {
  it("finds a cookie among others", () => {
    expect(readCookie("ap_csrf", "theme=dark; ap_csrf=abc-123; x=1")).toBe("abc-123");
    expect(readCookie("ap_csrf", "ap_csrf_old=1")).toBeNull();
    expect(readCookie("ap_csrf", "")).toBeNull();
  });
});

describe("withCsrf", () => {
  it("sends the token with mutating requests only", async () => {
    const { send, sent } = server([]);
    const fetch = withCsrf(send, () => "token");
    await fetch(new Request(URL, { method: "POST", body: "{}" }));
    await fetch(new Request(URL));
    expect(sent.map((request) => request.token)).toEqual(["token", null]);
  });

  it("repeats a refused request once with the new token", async () => {
    let token: string | null = null;
    const { send, sent } = server([refused()]);
    const fetch = withCsrf(
      async (request) => {
        const response = await send(request);
        token = "fresh"; // the refusal sets the cookie
        return response;
      },
      () => token,
    );
    const response = await fetch(new Request(URL, { method: "POST", body: '{"code":"x"}' }));
    expect(response.status).toBe(204);
    expect(sent).toEqual([
      { token: null, body: '{"code":"x"}' },
      { token: "fresh", body: '{"code":"x"}' },
    ]);
  });

  it("does not repeat without a new token or after another refusal", async () => {
    const same = server([refused()]);
    const response = await withCsrf(same.send, () => "token")(new Request(URL, { method: "POST" }));
    expect((await response.json()).code).toBe("CSRF_FAILED");
    expect(same.sent).toHaveLength(1);

    const forbidden = server([Response.json({ code: "HEAVY_NOT_ALLOWED" }, { status: 403 })]);
    let token = "a";
    const other = await withCsrf(
      forbidden.send,
      () => (token += "a"),
    )(new Request(URL, { method: "POST" }));
    expect(other.status).toBe(403);
    expect(forbidden.sent).toHaveLength(1);
  });
});
