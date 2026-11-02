import { expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";

const BASE = "http://localhost";
const client = createApiClient({ baseUrl: BASE });

/** The session cookie a response sets, as the browser would send it back. */
function session(response: Response): Record<string, string> {
  const cookie = response.headers.get("Set-Cookie")?.split(";")[0] ?? "";
  return { Cookie: cookie };
}

async function signIn(email: string) {
  const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
  await client.POST("/api/v1/auth/email/request", { body: { email, next: "/problems/mux4" } });
  const token = /#token=(\S+)/.exec(String(info.mock.calls[0]?.[0]))?.[1] ?? "";
  info.mockRestore();
  return client.POST("/api/v1/auth/email/verify", { body: { token } });
}

it("signs in by a login link and creates the user of a new address", async () => {
  const { data, response } = await signIn("Grace.Hopper@example.com");
  expect(data).toMatchObject({ created: true, next: "/problems/mux4" });
  expect(data?.user.nick).toBe("grace.hopper");
  const me = await client.GET("/api/v1/me", { headers: session(response) });
  expect(me.data?.email).toBe("grace.hopper@example.com");
  expect((await client.GET("/api/v1/me")).response.status).toBe(401);
});

it("rejects an expired login link", async () => {
  const { error } = await client.POST("/api/v1/auth/email/verify", {
    body: { token: "mock-expired-0000000000" },
  });
  expect(error?.code).toBe("LOGIN_LINK_INVALID");
});

it("shows the statuses of the signed-in user in the catalogue", async () => {
  const headers = session((await signIn("ada@example.com")).response);
  const { data } = await client.GET("/api/v1/problems", {
    params: { query: { status: ["solved"] } },
    headers,
  });
  expect(data?.items.map((item) => item.slug)).toEqual(["mux4", "carry-adder"]);
  expect(data?.progress[0]).toEqual({ difficulty: "easy", total: 3, solved: 2 });
  const guest = await client.GET("/api/v1/problems");
  expect(guest.data?.items[0]?.status).toBeNull();
  expect(guest.data?.progress[0]?.solved).toBeNull();
});

it("keeps drafts, changes the nick once in 30 days and schedules deletion", async () => {
  const headers = session((await signIn("ada@example.com")).response);
  const saved = await client.PUT("/api/v1/me/drafts/{slug}", {
    params: { path: { slug: "mux4" } },
    body: { code: "module mux4; endmodule", problem_version: 2 },
    headers,
  });
  expect(saved.data?.code).toBe("module mux4; endmodule");
  const draft = await client.GET("/api/v1/me/drafts/{slug}", {
    params: { path: { slug: "mux4" } },
    headers,
  });
  expect(draft.data?.problem_version).toBe(2);

  const renamed = await client.PATCH("/api/v1/me", { body: { nick: "ada-l" }, headers });
  expect(renamed.data?.nick_change_available_at).not.toBeNull();
  const again = await client.PATCH("/api/v1/me", { body: { nick: "ada-2" }, headers });
  expect(again.error?.code).toBe("NICK_CHANGE_TOO_SOON");
  expect(
    (await client.GET("/api/v1/users/{nick}", { params: { path: { nick: "ada-l" } } })).data
      ?.solved,
  ).toHaveLength(2);

  const deleting = await client.DELETE("/api/v1/me", { headers });
  expect(deleting.response.status).toBe(202);
  expect(deleting.data?.delete_at).not.toBeNull();
  const hidden = await client.GET("/api/v1/users/{nick}", { params: { path: { nick: "ada-l" } } });
  expect(hidden.response.status).toBe(404);
  const restored = await client.POST("/api/v1/me/restore", { headers });
  expect(restored.data?.delete_at).toBeNull();
});

it("returns from GitHub to the page of the login", async () => {
  const login = await fetch(`${BASE}/api/v1/auth/github/login?next=/problems/mux4`, {
    redirect: "manual",
  });
  const callback = await fetch(login.headers.get("Location") ?? "", { redirect: "manual" });
  expect(callback.status).toBe(302);
  expect(callback.headers.get("Location")).toBe("/problems/mux4");
  const me = await client.GET("/api/v1/me", { headers: session(callback) });
  expect(me.data?.nick).toBe("ada");
});
