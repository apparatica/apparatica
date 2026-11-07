// The page number in the address of a paged list (specs/08 §1): `?page=N`.

export type SearchParams = Record<string, string | string[] | undefined>;

/** A broken value opens the first page. */
export function parsePage(params: SearchParams): number {
  const value = Array.isArray(params.page) ? params.page[0] : params.page;
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 1 ? page : 1;
}
