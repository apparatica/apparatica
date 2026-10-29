// Requests of the submission feature.
import { apiUrl, browserApi as api } from "@/lib/api/browser";
import { markGone, rememberSubmissions } from "@/features/guest/submissions";
import type { Schemas } from "@/lib/api/client";

export { api };

export const eventsUrl = (id: string) =>
  apiUrl(`/api/v1/submissions/${encodeURIComponent(id)}/events`);

export const submissionKeys = {
  all: ["submissions"] as const,
  detail: (id: string) => ["submissions", "detail", id] as const,
  list: (problem: string) => ["submissions", "list", problem] as const,
  recent: (problem: string, wanted: string | null) =>
    ["submissions", "recent", problem, wanted] as const,
};

export async function getSubmission(id: string): Promise<Schemas["Submission"]> {
  const { data, error } = await api.GET("/api/v1/submissions/{id}", {
    params: { path: { id } },
  });
  if (error !== undefined) throw error;
  return data;
}

/** As many as the API gives at once: the list of a problem is usually one page. */
const PAGE_LIMIT = 100;

/** The submissions of the guest for the problem (one page, the newest) go to the local history. */
export async function syncSubmissions(problem: string): Promise<Schemas["SubmissionPage"]> {
  const { data, error } = await api.GET("/api/v1/submissions", {
    params: { query: { problem, limit: PAGE_LIMIT } },
  });
  if (error !== undefined) throw error;
  rememberSubmissions(data.items, data.next_cursor === null ? { problem } : null);
  return data;
}

/** The submissions of the guest for the problem go to the local history (one page, the newest);
 * the result is the one to show — `wanted` if the page was opened for it, else the last one — and
 * the quotas. */
export async function getRecent(
  problem: string,
  wanted: string | null = null,
): Promise<{
  submission: Schemas["Submission"] | null;
  quota: Schemas["QuotaStatus"] | null;
}> {
  const data = await syncSubmissions(problem);
  const found = wanted === null ? null : await findSubmission(wanted, problem);
  const last = data.items[0];
  return {
    submission: found ?? (last === undefined ? null : await getSubmission(last.id)),
    quota: data.quota,
  };
}

/** The submission of the problem; null when the server no longer has it (it is marked gone in the
 * local history) or it is of another problem. */
export async function findSubmission(
  id: string,
  problem: string,
): Promise<Schemas["Submission"] | null> {
  try {
    const submission = await getSubmission(id);
    return submission.problem === problem ? submission : null;
  } catch (error) {
    if (!isNotFound(error)) throw error;
    markGone(id);
    return null;
  }
}

export const isNotFound = (error: unknown): boolean =>
  typeof error === "object" && error !== null && "status" in error && error.status === 404;
