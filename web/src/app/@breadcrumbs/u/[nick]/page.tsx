import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { loadProfile } from "@/features/profile/load";

// The mock-up's «Участники / nick»: there is no page of participants yet, so only the nick.
export default async function ProfileBreadcrumbs({ params }: PageProps<"/u/[nick]">) {
  const data = await loadProfile((await params).nick);
  if (data === null) return null;
  return <Breadcrumbs items={[{ label: data.profile.nick }]} />;
}
