import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";

import { columnSort, DEFAULT_QUERY, leaderboardHref, parseBoardQuery } from "./query";

const ORDER: Schemas["LeaderboardKey"][] = [
  { metric: "synth.critical_path_ns", dir: "asc" },
  { metric: "synth.area_um2", dir: "asc" },
];

it("reads the query of the address and drops what it does not understand", () => {
  expect(parseBoardQuery({})).toEqual(DEFAULT_QUERY);
  expect(parseBoardQuery({ page: "3", sort: "-synth.area_um2", group: "0", around: "me" })).toEqual(
    { page: 3, sort: "-synth.area_um2", group: false, around: true },
  );
  expect(parseBoardQuery({ page: "-1", sort: "drop table", group: "no" })).toEqual(DEFAULT_QUERY);
  expect(parseBoardQuery({ page: ["2", "5"] }).page).toBe(2);
});

it("writes the address without the defaults", () => {
  expect(leaderboardHref("sync-fifo")).toBe("/problems/sync-fifo/leaderboard");
  expect(leaderboardHref("sync-fifo", { page: 2, sort: "synth.cells", group: false })).toBe(
    "/problems/sync-fifo/leaderboard?page=2&sort=synth.cells&group=0",
  );
  // «К моей строке»: the server picks the page.
  expect(leaderboardHref("sync-fifo", { page: 4, around: true })).toBe(
    "/problems/sync-fifo/leaderboard?around=me",
  );
});

it("lets the main metric stand for the order of places", () => {
  expect(columnSort("synth.critical_path_ns", "rank", ORDER)).toEqual({
    active: true,
    dir: "asc",
    next: "-synth.critical_path_ns",
  });
  expect(columnSort("synth.critical_path_ns", "-synth.critical_path_ns", ORDER)).toEqual({
    active: true,
    dir: "desc",
    next: "rank",
  });
  expect(columnSort("synth.critical_path_ns", "synth.cells", ORDER)).toMatchObject({
    active: false,
    next: "rank",
  });
});

it("sorts other columns better values first, then the other way", () => {
  expect(columnSort("synth.area_um2", "rank", ORDER)).toEqual({
    active: false,
    dir: "asc",
    next: "synth.area_um2",
  });
  expect(columnSort("synth.area_um2", "synth.area_um2", ORDER)).toEqual({
    active: true,
    dir: "asc",
    next: "-synth.area_um2",
  });
  expect(columnSort("synth.area_um2", "-synth.area_um2", ORDER).next).toBe("synth.area_um2");
  // A metric the formula maximizes starts from the highest.
  const order: Schemas["LeaderboardKey"][] = [...ORDER, { metric: "synth.fmax_mhz", dir: "desc" }];
  expect(columnSort("synth.fmax_mhz", "rank", order).next).toBe("-synth.fmax_mhz");
});

it("starts the dates from the newest", () => {
  expect(columnSort("submitted_at", "rank", ORDER).next).toBe("-submitted_at");
  expect(columnSort("submitted_at", "-submitted_at", ORDER)).toEqual({
    active: true,
    dir: "desc",
    next: "submitted_at",
  });
});
