"use client";

// Who looks at the page, for what differs for a guest: the menu of the header, the hints to log in
// on the problem page (sheet Guest). The session cookie is httpOnly: the server of the site sees it
// and passes it down, GET /me confirms it; an ended session turns into a guest.
import { createContext, type ReactNode, use } from "react";

import type { Me } from "./api";
import { useMe } from "./use-me";

const SessionCookie = createContext(false);

/** `signedIn`: the browser has a session cookie. */
export function SessionProvider({
  signedIn,
  children,
}: {
  signedIn: boolean;
  children: ReactNode;
}) {
  return <SessionCookie value={signedIn}>{children}</SessionCookie>;
}

/** The signed-in user: undefined while loading, null for a guest. Without a session cookie nothing
 * is requested. */
export function useAccount(): Me | null | undefined {
  const signedIn = use(SessionCookie);
  const { data: me, isError } = useMe(signedIn);
  if (!signedIn || isError) return null;
  return me;
}

/** A guest for sure: the hints to log in wait while a session is being checked. */
export function useGuest(): boolean {
  return useAccount() === null;
}
