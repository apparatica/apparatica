// Requests of the submission feature: the browser talks to the API on the site's origin.
import { createApiClient, type Schemas } from "@/lib/api/client";

const origin = globalThis.location?.origin ?? "";

export const api = createApiClient({ baseUrl: origin });

export const eventsUrl = (id: string) =>
  `${origin}/api/v1/submissions/${encodeURIComponent(id)}/events`;

export const submissionKeys = {
  all: ["submissions"] as const,
  detail: (id: string) => ["submissions", "detail", id] as const,
  latest: (problem: string) => ["submissions", "latest", problem] as const,
};

export async function getSubmission(id: string): Promise<Schemas["Submission"]> {
  const { data, error } = await api.GET("/api/v1/submissions/{id}", {
    params: { path: { id } },
  });
  if (error !== undefined) throw error;
  return data;
}

/** The last submission of the guest for the problem, and the quotas. */
export async function getLatest(problem: string): Promise<{
  submission: Schemas["Submission"] | null;
  quota: Schemas["QuotaStatus"] | null;
}> {
  const { data, error } = await api.GET("/api/v1/submissions", {
    params: { query: { problem, limit: 1 } },
  });
  if (error !== undefined) throw error;
  const [last] = data.items;
  return {
    submission: last === undefined ? null : await getSubmission(last.id),
    quota: data.quota,
  };
}
