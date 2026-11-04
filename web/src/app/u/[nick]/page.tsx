import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { profileHref } from "@/features/profile/href";
import { loadProfile } from "@/features/profile/load";
import { ProfileView } from "@/features/profile/profile-view";

export async function generateMetadata({ params }: PageProps<"/u/[nick]">): Promise<Metadata> {
  const data = await loadProfile((await params).nick);
  if (data === null) return {};
  const t = await getTranslations("profile");
  const { nick, progress } = data.profile;
  const solved = progress.reduce((sum, level) => sum + level.solved, 0);
  const total = progress.reduce((sum, level) => sum + level.total, 0);
  const description = t("description", { nick, solved, total });
  return { title: nick, description, openGraph: { title: nick, description, type: "profile" } };
}

export default async function ProfilePage({ params }: PageProps<"/u/[nick]">) {
  const nick = (await params).nick;
  // Nicks are lowercase and unique in any case: /u/Ada is the profile of ada.
  if (nick !== nick.toLowerCase()) permanentRedirect(profileHref(nick.toLowerCase()));
  const data = await loadProfile(nick);
  if (data === null) notFound();
  return <ProfileView {...data} />;
}
