"use client";

import { useQuery } from "@tanstack/react-query";

import { getMe, meKey } from "./api";

/** The signed-in user: undefined while loading, null for a guest. Without `enabled` (no session
 * cookie, so a guest) nothing is requested. */
export function useMe(enabled = true) {
  return useQuery({ queryKey: meKey, queryFn: getMe, enabled });
}
