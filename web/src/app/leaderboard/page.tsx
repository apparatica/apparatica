import type { Metadata } from "next";
import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";

import { loadRating } from "@/features/rating/load";
import { parseRatingPage } from "@/features/rating/query";
import { RatingPage } from "@/features/rating/rating-page";
import { SESSION_COOKIE } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("rating");
  const title = t("metaTitle");
  const description = t("description");
  return { title, description, openGraph: { title, description, type: "website" } };
}

// The global leaderboard (FR-LB-05): the server renders the page of the address as the user of
// the request sees it.
export default async function GlobalLeaderboardPage({ searchParams }: PageProps<"/leaderboard">) {
  const session = (await cookies()).get(SESSION_COOKIE)?.value ?? null;
  const data = await loadRating(parseRatingPage(await searchParams), session);
  return <RatingPage {...data} />;
}
