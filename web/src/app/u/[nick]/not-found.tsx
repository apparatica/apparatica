import { NotFoundState } from "@/features/errors/states";

// Nobody has the nick, or the account is being deleted (FR-USR-04).
export default function ProfileNotFound() {
  return <NotFoundState kind="profile" />;
}
