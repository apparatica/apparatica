// The sizes of the panels of the problem page (FR-PRB-01), remembered by the browser in a cookie:
// the server renders the page with them, so the panels do not jump after hydration.

export const LAYOUT_COOKIE = "ap_bench";
const ONE_YEAR_S = 60 * 60 * 24 * 365;

/** Panel id → percentage of its group. */
export type PanelSizes = Record<string, number>;

export interface BenchLayout {
  /** The statement and the work column. */
  columns: PanelSizes;
  /** The editor and the results, in the work column. */
  rows: PanelSizes;
}

export const PANELS = {
  columns: ["statement", "work"],
  rows: ["editor", "results"],
} as const satisfies Record<keyof BenchLayout, readonly string[]>;

function parseSizes(value: unknown, ids: readonly string[]): PanelSizes | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const sizes = value as Record<string, unknown>;
  const valid = ids.every((id) => {
    const size = sizes[id];
    return typeof size === "number" && size > 0 && size < 100;
  });
  if (!valid || Object.keys(sizes).length !== ids.length) return undefined;
  const total = ids.reduce((sum, id) => sum + (sizes[id] as number), 0);
  return Math.abs(total - 100) < 1 ? (sizes as PanelSizes) : undefined;
}

/** The layout of the cookie, each group on its own: a broken group gets the default sizes. */
export function parseBenchLayout(value: string | undefined): Partial<BenchLayout> {
  if (value === undefined) return {};
  try {
    const data = JSON.parse(decodeURIComponent(value)) as Record<string, unknown> | null;
    const columns = parseSizes(data?.["columns"], PANELS.columns);
    const rows = parseSizes(data?.["rows"], PANELS.rows);
    return { ...(columns && { columns }), ...(rows && { rows }) };
  } catch {
    return {};
  }
}

export function benchLayoutCookie(layout: Partial<BenchLayout>): string {
  const value = encodeURIComponent(JSON.stringify(layout));
  return `${LAYOUT_COOKIE}=${value}; Path=/problems; Max-Age=${ONE_YEAR_S}; SameSite=Lax`;
}

/** The cookie value of a `Cookie` header or of `document.cookie`. */
export function layoutCookieValue(cookies: string): string | undefined {
  const prefix = `${LAYOUT_COOKIE}=`;
  return cookies
    .split("; ")
    .find((cookie) => cookie.startsWith(prefix))
    ?.slice(prefix.length);
}

/** Remembers the sizes of one group in the browser, keeping the other one. */
export function saveBenchLayout(group: keyof BenchLayout, sizes: PanelSizes): void {
  const layout = parseBenchLayout(layoutCookieValue(document.cookie));
  document.cookie = benchLayoutCookie({ ...layout, [group]: sizes });
}
