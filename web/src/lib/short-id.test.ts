import { expect, it } from "vitest";

import { fromShortId, shortHref, toShortId } from "./short-id";

const ID = "6f1d2c3b-4a59-4e87-9d10-0b2c3d4e5f60";

it("writes a UUID in base62 and reads it back", () => {
  const short = toShortId(ID);
  expect(short).toMatch(/^[0-9A-Za-z]{1,22}$/);
  expect(fromShortId(short)).toBe(ID);
  expect(shortHref(ID)).toBe(`/s/${short}`);
});

it("keeps the edges of the range", () => {
  expect(toShortId("00000000-0000-0000-0000-000000000000")).toBe("0");
  expect(fromShortId("0")).toBe("00000000-0000-0000-0000-000000000000");
  const max = "ffffffff-ffff-ffff-ffff-ffffffffffff";
  expect(toShortId(max)).toHaveLength(22);
  expect(fromShortId(toShortId(max))).toBe(max);
});

it("reads an upper-case UUID as the same id", () => {
  expect(fromShortId(toShortId(ID.toUpperCase()))).toBe(ID);
});

it("refuses what is no short id of a UUID", () => {
  expect(fromShortId("")).toBeNull();
  expect(fromShortId("abc-def")).toBeNull();
  // Leading zeros would give one UUID two links.
  expect(fromShortId(`0${toShortId(ID)}`)).toBeNull();
  // Over 2^128 − 1.
  expect(fromShortId("zzzzzzzzzzzzzzzzzzzzzz")).toBeNull();
  expect(fromShortId("1".repeat(23))).toBeNull();
  expect(() => toShortId("2917")).toThrow();
});
