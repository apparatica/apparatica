// The data of a profile page, read by the server from the API. The page, its metadata and the
// breadcrumbs slot of the layout ask for it in one request: `cache` reads it once.
import { cache } from "react";

import type { ApiError, Schemas } from "@/lib/api/client";
import { serverApi } from "@/lib/api/server";

export interface ProfileData {
  profile: Schemas["Profile"];
  levels: Schemas["Difficulty"][];
}

function data<T>(result: { data?: T; error?: ApiError }, what: string): T {
  if (result.data === undefined) {
    throw new Error(
      `${what}: ${result.error?.code ?? "no response"} ${result.error?.detail ?? ""}`,
    );
  }
  return result.data;
}

/** null for a nick nobody has (or one the API rejects): the page is a 404. */
export const loadProfile = cache(async (nick: string): Promise<ProfileData | null> => {
  const [found, config] = await Promise.all([
    serverApi.GET("/api/v1/users/{nick}", { params: { path: { nick } } }),
    serverApi.GET("/api/v1/config").then((result) => data(result, "GET /config")),
  ]);
  if (found.error?.code === "NOT_FOUND" || found.error?.code === "VALIDATION_ERROR") return null;
  return { profile: data(found, `GET /users/${nick}`), levels: config.difficulties };
});
