// The page of the global leaderboard in its address (specs/08 §1): only the page number.
import { parsePage } from "@/lib/page-param";

/** Rows of a page. */
export const RATING_PER_PAGE = 20;

export const RATING_PATH = "/leaderboard";

/** A broken value opens the first page. */
export const parseRatingPage = parsePage;

export const ratingHref = (page = 1): string =>
  page > 1 ? `${RATING_PATH}?page=${page}` : RATING_PATH;
