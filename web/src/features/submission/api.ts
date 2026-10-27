// Requests of the submission feature.
import { apiUrl, browserApi as api } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";

export { api };

export const eventsUrl = (id: string) =>
  apiUrl(`/api/v1/submissions/${encodeURIComponent(id)}/events`);

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
