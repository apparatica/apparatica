"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { Avatar } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { notify } from "@/components/ui/toast";
import { logout, type Me, meKey } from "@/features/account/api";
import { useMe } from "@/features/account/use-me";

import { DocumentsItem, GuestMenu, ThemeItems } from "./guest-menu";

/** The avatar and the nick of the signed-in user (mock-up Dashboard) and their menu; the «Гость»
 * chip for a guest. `signedIn`: the browser has a session cookie, so the server renders a
 * placeholder rather than «Гость» while the user loads; an ended session turns into a guest. */
export function AccountMenu({ signedIn }: { signedIn: boolean }) {
  const { data: me, isError } = useMe(signedIn);
  if (!signedIn || me === null || isError) return <GuestMenu />;
  if (me === undefined) return <Skeleton className="h-5 w-20" />;
  return <UserMenu me={me} />;
}

export function UserMenu({ me }: { me: Me }) {
  const t = useTranslations("shell.account");
  const queryClient = useQueryClient();
  const router = useRouter();
  const signOut = async () => {
    try {
      await logout();
    } catch {
      notify({ tone: "er", title: t("logoutFailed") });
      return;
    }
    queryClient.setQueryData(meKey, null);
    router.refresh(); // the server renders the page of a guest
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("menu", { nick: me.nick })}
        className="inline-flex h-[26px] max-w-40 cursor-pointer items-center gap-2 rounded-md px-1 text-[12.5px] hover:bg-sf2 data-[state=open]:bg-sf2 pointer-coarse:h-11"
      >
        <Avatar name={me.display_name ?? me.nick} src={me.avatar_url} size={20} />
        <span className="truncate max-sm:sr-only">{me.nick}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <div className="flex max-w-60 flex-col px-2 py-1.5 text-[12.5px]">
          <span className="truncate font-medium">{me.display_name ?? me.nick}</span>
          {me.email !== null && <span className="truncate text-caption text-mu">{me.email}</span>}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings aria-hidden="true" />
            {t("settings")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <ThemeItems />
        <DropdownMenuSeparator />
        <DocumentsItem />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut aria-hidden="true" />
          {t("logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
