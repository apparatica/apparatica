// The data of a solution page, read by the server from the API as the visitor of the request sees
// it: the code opens after the visitor's own accepted Submit of the problem, of a user or a guest
// (FR-SOL-02), so the session and the guest cookie go with the request. The page, its metadata
// and the breadcrumbs slot ask for it in one request: `cache` reads it once.
import { cache } from "react";

import type { Schemas } from "@/lib/api/client";
import { visitorApi } from "@/lib/api/server";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** null when there is no such public solution (or the id is no UUID): the page is a 404. */
export const loadSolution = cache(
  async (
    id: string,
    session: string | null,
    guest: string | null,
  ): Promise<Schemas["Solution"] | null> => {
    if (!UUID.test(id)) return null;
    const { data, error, response } = await visitorApi({ session, guest }).GET(
      "/api/v1/solutions/{id}",
      { params: { path: { id } } },
    );
    if (response.status === 404 || response.status === 422) return null;
    if (data === undefined) {
      throw new Error(
        `GET /solutions/${id}: ${error?.code ?? "no response"} ${error?.detail ?? ""}`,
      );
    }
    return data;
  },
);
