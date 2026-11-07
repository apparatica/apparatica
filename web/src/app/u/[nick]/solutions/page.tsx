import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { userSolutionsHref } from "@/features/profile/href";
import { loadUserSolutions } from "@/features/profile/load";
import { UserSolutionsPage } from "@/features/profile/solutions-page";
import { parsePage } from "@/lib/page-param";

export async function generateMetadata({
  params,
}: PageProps<"/u/[nick]/solutions">): Promise<Metadata> {
  const { nick } = await params;
  const t = await getTranslations("profile.solutionsPage");
  const title = t("metaTitle", { nick });
  const description = t("description", { nick });
  return { title, description, openGraph: { title, description, type: "website" } };
}

// The public solutions of a user, page by page (FR-USR-04): the same for every visitor.
export default async function UserSolutions({
  params,
  searchParams,
}: PageProps<"/u/[nick]/solutions">) {
  const { nick } = await params;
  const page = parsePage(await searchParams);
  if (nick !== nick.toLowerCase()) permanentRedirect(userSolutionsHref(nick.toLowerCase(), page));
  const data = await loadUserSolutions(nick, page);
  if (data === null) notFound();
  return <UserSolutionsPage nick={data.nick} solutions={data.solutions} />;
}
