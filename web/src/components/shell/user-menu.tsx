"use client";

import { LogOut, Settings, ShieldCheck, User } from "lucide-react";
import Link from "next/link";
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
import { afterLogout, logout, type Me } from "@/features/account/api";
import { useAccount } from "@/features/account/session";
import { profileHref } from "@/features/profile/href";

import { DocumentsItem, GuestMenu, ThemeItems } from "./guest-menu";

/** The avatar and the nick of the signed-in user (mock-up Dashboard) and their menu; the «Гость»
 * chip for a guest. With a session cookie the server renders a placeholder rather than «Гость»
 * while the user loads. */
export function AccountMenu() {
  const me = useAccount();
  if (me === null) return <GuestMenu />;
  if (me === undefined) return <Skeleton className="h-5 w-20" />;
  return <UserMenu me={me} />;
}

/** Roles that open the admin panel (FR-ADM-02). */
const STAFF: readonly Me["role"][] = ["moderator", "admin"];

export function UserMenu({ me }: { me: Me }) {
  const t = useTranslations("shell.account");
  const signOut = async () => {
    try {
      await logout();
    } catch {
      notify({ tone: "er", title: t("logoutFailed") });
      return;
    }
    afterLogout.reload();
  };
  return (
    <DropdownMenu>
      {/* Named by the visible nick, as the «Гость» chip by its label (WCAG 2.5.3). */}
      <DropdownMenuTrigger className="inline-flex h-[26px] max-w-40 cursor-pointer items-center gap-2 rounded-md px-1 text-[12.5px] hover:bg-sf2 data-[state=open]:bg-sf2 pointer-coarse:h-11">
        <span aria-hidden="true" className="flex">
          <Avatar name={me.display_name ?? me.nick} src={me.avatar_url} size={20} />
        </span>
        <span className="truncate max-sm:sr-only">{me.nick}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <div className="flex max-w-60 flex-col px-2 py-1.5 text-[12.5px]">
          <span className="truncate font-medium">{me.display_name ?? me.nick}</span>
          {me.email !== null && <span className="truncate text-caption text-mu">{me.email}</span>}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href={profileHref(me.nick)}>
            <User aria-hidden="true" />
            {t("profile")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings aria-hidden="true" />
            {t("settings")}
          </Link>
        </DropdownMenuItem>
        {STAFF.includes(me.role) && (
          <DropdownMenuItem asChild>
            {/* The admin panel is served by the API, not by the site: a full page load. */}
            <a href="/admin">
              <ShieldCheck aria-hidden="true" />
              {t("moderation")}
            </a>
          </DropdownMenuItem>
        )}
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
