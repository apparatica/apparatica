/** The address of the profile of a nick (FR-USR-04). */
export const profileHref = (nick: string): string => `/u/${nick}`;

/** The public solutions of a nick, page by page. */
export const userSolutionsHref = (nick: string, page = 1): string =>
  `${profileHref(nick)}/solutions${page > 1 ? `?page=${page}` : ""}`;
