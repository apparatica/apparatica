// The page of the global leaderboard in its address (specs/08 §1): only the page number.

/** Rows of a page. */
export const RATING_PER_PAGE = 20;

export const RATING_PATH = "/leaderboard";

type SearchParams = Record<string, string | string[] | undefined>;

/** A broken value opens the first page. */
export function parseRatingPage(params: SearchParams): number {
  const value = Array.isArray(params.page) ? params.page[0] : params.page;
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 1 ? page : 1;
}

export const ratingHref = (page = 1): string =>
  page > 1 ? `${RATING_PATH}?page=${page}` : RATING_PATH;
