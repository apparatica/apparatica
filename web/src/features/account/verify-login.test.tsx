import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";

import { linkToken, navigation, VerifyLogin } from "./verify-login";

const open = vi.spyOn(navigation, "open");

beforeEach(() => {
  open.mockReset().mockImplementation(() => undefined);
});
afterEach(() => history.replaceState(null, "", "/"));

function visit(fragment: string) {
  history.replaceState(null, "", `/login/email/verify${fragment}`);
  return renderWithProviders(
    <StrictMode>
      <VerifyLogin />
    </StrictMode>,
  );
}

/** Counts the requests of POST /auth/email/verify; the mocks answer. */
function countVerifications(): { count: number } {
  const seen = { count: 0 };
  server.use(
    http.post(api("/api/v1/auth/email/verify"), () => {
      seen.count += 1;
      return undefined;
    }),
  );
  return seen;
}

it("reads the token of the fragment", () => {
  expect(linkToken("#token=abc")).toBe("abc");
  expect(linkToken("#other=1&token=a%2Bb")).toBe("a+b");
  expect(linkToken("#token=")).toBeNull();
  expect(linkToken("")).toBeNull();
});

it("signs in once with the token and opens the site", async () => {
  const seen = countVerifications();
  visit("#token=mock-1");
  expect(screen.getByRole("heading", { name: "Входим…" })).toBeInTheDocument();
  // The token leaves the address at once.
  expect(location.hash).toBe("");
  expect(location.pathname).toBe("/login/email/verify");
  await waitFor(() => expect(open).toHaveBeenCalledWith("/"));
  expect(seen.count).toBe(1);
});

it("returns to next, but only to a page of the site", async () => {
  const me: Schemas["Me"] = {
    id: "00000000-0000-4000-8000-000000000001",
    nick: "ada",
    display_name: null,
    avatar_url: null,
    email: "ada@example.com",
    role: "user",
    created_at: "2026-09-14T10:00:00Z",
    nick_change_available_at: null,
    delete_at: null,
  };
  let next = "/problems/mux4?tab=submissions";
  server.use(
    http.post(api("/api/v1/auth/email/verify"), () =>
      HttpResponse.json<Schemas["EmailLogin"]>({ user: me, created: false, next }),
    ),
  );
  const { unmount } = visit("#token=mock-2");
  await waitFor(() => expect(open).toHaveBeenCalledWith("/problems/mux4?tab=submissions"));
  unmount();

  next = "//evil.example/";
  visit("#token=mock-3");
  await waitFor(() => expect(open).toHaveBeenLastCalledWith("/"));
});

it("offers a new link when the link is used or expired", async () => {
  visit("#token=expired-1");
  expect(await screen.findByRole("heading", { name: "Ссылка не подходит" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Получить новую ссылку" })).toHaveAttribute(
    "href",
    "/login",
  );
  expect(open).not.toHaveBeenCalled();
});

it("does not ask the API without a token", async () => {
  const seen = countVerifications();
  visit("");
  expect(await screen.findByRole("heading", { name: "Ссылка не подходит" })).toBeInTheDocument();
  expect(seen.count).toBe(0);
});
