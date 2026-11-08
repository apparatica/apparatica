// How an author is named on the site: by the nick, with a link to the profile. The public solutions
// of a deleted account stay under «удалённый участник» (ОВ-12), who has no profile. Russian needs
// the genitive in «Решение {nick}», which a nick does not change.
import { useTranslations } from "next-intl";

import type { Schemas } from "@/lib/api/client";

import { profileHref } from "./href";

type Author = Pick<Schemas["UserRef"], "nick" | "deleted">;
type Words = (key: "deleted" | "deletedOf") => string;

export interface AuthorNames {
  /** «удалённый участник» */
  name: (author: Author) => string;
  /** «удалённого участника»: after «Решение». */
  of: (author: Author) => string;
  /** The profile; null: there is none. */
  href: (author: Author) => string | null;
  /** The props of an author in a row of a leaderboard. */
  row: (author: Author) => { nick: string; of: string; href: string | null };
}

/** For server code: `authorNames(await getTranslations("author"))`. */
export function authorNames(t: Words): AuthorNames {
  const name = (author: Author) => (author.deleted ? t("deleted") : author.nick);
  const of = (author: Author) => (author.deleted ? t("deletedOf") : author.nick);
  const href = (author: Author) => (author.deleted ? null : profileHref(author.nick));
  return {
    name,
    of,
    href,
    row: (author) => ({ nick: name(author), of: of(author), href: href(author) }),
  };
}

export function useAuthorNames(): AuthorNames {
  return authorNames(useTranslations("author"));
}
