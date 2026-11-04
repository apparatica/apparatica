"use client";

// Who looks at the page, for what differs for a guest: the menu of the header, the hints to log in
// on the problem page (sheet Guest), whose history the local stores hold. The session cookie is
// httpOnly: the server of the site sees it and passes it down, GET /me confirms it; an ended
// session turns into a guest. A login and a logout load the page anew.
import { createContext, type ReactNode, use, useEffect, useState } from "react";

import { setStoreOwner } from "@/features/guest/local-store";

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
  const { data: me } = useMe(signedIn);
  const owner = signedIn && me !== null ? "user" : "guest"; // null: the session has ended
  // Once before the children first read the stores (they render after this), later on changes.
  useState(() => {
    if (typeof window !== "undefined") setStoreOwner(owner);
  });
  useEffect(() => setStoreOwner(owner), [owner]);
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
