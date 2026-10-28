import { afterEach, expect, it, vi } from "vitest";

import { DRAFT_PREFIX, readDraft, writeDraft } from "./drafts";

afterEach(() => vi.restoreAllMocks());

it("saves a draft per problem and reads it back", () => {
  const now = new Date("2026-10-28T09:30:00Z");
  expect(writeDraft("sync-fifo", { code: "module m; endmodule", version: 2 }, now)).toEqual({
    code: "module m; endmodule",
    version: 2,
    savedAt: "2026-10-28T09:30:00.000Z",
  });
  writeDraft("mux4", { code: "module mux4; endmodule", version: 1 }, now);
  expect(readDraft("sync-fifo")?.code).toBe("module m; endmodule");
  expect(readDraft("mux4")?.version).toBe(1);
  expect(readDraft("counter-mod-n")).toBeNull();
});

it.each([
  "not json",
  "null",
  JSON.stringify({ v: 2, code: "x", version: 1, savedAt: "2026-10-28T09:30:00Z" }),
  JSON.stringify({ v: 1, code: 1, version: 1, savedAt: "2026-10-28T09:30:00Z" }),
  JSON.stringify({ v: 1, code: "x", version: 1.5, savedAt: "2026-10-28T09:30:00Z" }),
  JSON.stringify({ v: 1, code: "x", version: 1, savedAt: "вчера" }),
])("ignores a broken draft %s", (raw) => {
  localStorage.setItem(`${DRAFT_PREFIX}sync-fifo`, raw);
  expect(readDraft("sync-fifo")).toBeNull();
});

it("survives disabled or full storage", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("full", "QuotaExceededError");
  });
  expect(writeDraft("sync-fifo", { code: "x", version: 1 })).toBeNull();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("denied", "SecurityError");
  });
  expect(readDraft("sync-fifo")).toBeNull();
});
