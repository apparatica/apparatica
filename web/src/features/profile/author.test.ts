import { expect, it } from "vitest";

import { authorNames } from "./author";

const names = authorNames((key) =>
  key === "deleted" ? "удалённый участник" : "удалённого участника",
);

it("names an author by the nick, with the profile", () => {
  const author = { nick: "ada", deleted: false };
  expect(names.row(author)).toEqual({ nick: "ada", of: "ada", href: "/u/ada" });
});

it("names a deleted author in words, without a profile", () => {
  const author = { nick: "deleted-participant", deleted: true };
  expect(names.row(author)).toEqual({
    nick: "удалённый участник",
    of: "удалённого участника",
    href: null,
  });
});
