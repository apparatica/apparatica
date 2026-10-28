import { afterEach, describe, expect, it } from "vitest";

import {
  benchLayoutCookie,
  LAYOUT_COOKIE,
  layoutCookieValue,
  parseBenchLayout,
  saveBenchLayout,
} from "./layout";

const cookieValue = (cookie: string) => layoutCookieValue(cookie.split(";")[0] ?? "");

describe("bench layout cookie", () => {
  it("round-trips", () => {
    const layout = { columns: { statement: 40, work: 60 }, rows: { editor: 55.5, results: 44.5 } };
    expect(parseBenchLayout(cookieValue(benchLayoutCookie(layout)))).toEqual(layout);
  });

  it("keeps the valid group of a broken cookie", () => {
    const value = encodeURIComponent(
      JSON.stringify({ columns: { statement: 40, work: 60 }, rows: { editor: 90, results: 30 } }),
    );
    expect(parseBenchLayout(value)).toEqual({ columns: { statement: 40, work: 60 } });
  });

  it.each([undefined, "", "%E0", "null", "[]", '{"columns":{"statement":"40","work":60}}'])(
    "ignores %j",
    (value) => {
      expect(parseBenchLayout(value)).toEqual({});
    },
  );

  it("ignores unknown panels", () => {
    const value = encodeURIComponent(
      JSON.stringify({ columns: { statement: 40, work: 50, extra: 10 } }),
    );
    expect(parseBenchLayout(value)).toEqual({});
  });
});

describe("saveBenchLayout", () => {
  afterEach(() => {
    document.cookie = `${LAYOUT_COOKIE}=; Path=/problems; Max-Age=0`;
  });

  it("keeps the other group", () => {
    // jsdom keeps cookies of /problems away from the test page at /.
    window.history.replaceState(null, "", "/problems/sync-fifo");
    saveBenchLayout("columns", { statement: 30, work: 70 });
    saveBenchLayout("rows", { editor: 60, results: 40 });
    saveBenchLayout("columns", { statement: 45, work: 55 });
    expect(parseBenchLayout(layoutCookieValue(document.cookie))).toEqual({
      columns: { statement: 45, work: 55 },
      rows: { editor: 60, results: 40 },
    });
    window.history.replaceState(null, "", "/");
  });
});
