import { expect, it } from "vitest";

import { loginHref, sitePath } from "./session";

it("keeps only the paths of the site as next", () => {
  expect(sitePath("/problems/mux4?tab=submissions")).toBe("/problems/mux4?tab=submissions");
  expect(sitePath("https://evil.example/")).toBeNull();
  expect(sitePath("//evil.example/")).toBeNull();
  expect(sitePath("/\\evil.example/")).toBeNull();
  expect(sitePath("/a b")).toBeNull();
  expect(sitePath(["/settings"])).toBeNull();
  expect(sitePath(undefined)).toBeNull();
});

it("leads to the login page and back", () => {
  expect(loginHref("/settings")).toBe("/login?next=/settings");
  expect(loginHref("/problems?q=fifo&tag=memory")).toBe(
    "/login?next=/problems%3Fq%3Dfifo%26tag%3Dmemory",
  );
  expect(loginHref("/")).toBe("/login");
  expect(loginHref("/login?next=/settings")).toBe("/login");
  expect(loginHref("//evil.example/")).toBe("/login");
  expect(loginHref()).toBe("/login");
});
