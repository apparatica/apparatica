"use client";

// useSubmission: the check of a problem page (docs/frontend.md#проверка-usesubmission). Run and
// Submit create a submission, its event stream feeds the state, a dropped stream reconnects; an
// opened page restores the last submission of the problem and reads its stream to the end. A
// finished check goes to the local history of the guest (the catalogue shows it).
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";

import { recordCheck } from "@/features/guest/history";
import type { ApiError, Schemas } from "@/lib/api/client";

import { api, eventsUrl, getLatest, getSubmission, submissionKeys } from "./api";
import { type Check, isFinished, type Submission } from "./machine";
import { SubmissionStore } from "./store";
import type { Connection } from "./stream";

export interface StartInput {
  kind: Submission["kind"];
  code: string;
  /** A solved ALTCHA challenge after `428 CAPTCHA_REQUIRED`. */
  captcha?: string | null;
}

export interface UseSubmissionOptions {
  problem: string;
  version: number;
  /** The level of the problem, for the local history. */
  difficulty: string;
  /** Delays of the reconnects; RECONNECT_DELAYS_MS by default. */
  reconnectDelaysMs?: readonly number[] | undefined;
}

export interface SubmissionState {
  /** The live check: null before the first one (and while the last one is being restored). */
  check: Check | null;
  /** The stored submission: as created or restored, read again after `finalized`. */
  submission: Submission | null;
  /** The event stream of the check; null before it connects. */
  connection: Connection | null;
  quota: Schemas["QuotaStatus"] | null;
  /** The last submission of the problem is being looked up. */
  restoring: boolean;
  /** The kind being created: Run or Submit shows its progress. */
  starting: Submission["kind"] | null;
  cancelling: boolean;
  /** This page asked to cancel the check (and not another tab or a newer check). */
  cancelRequested: boolean;
  /** The last start or cancel failed: `problem+json` from the API or a network error. */
  error: ApiError | Error | null;
  start: (input: StartInput) => void;
  cancel: () => void;
  /** "Connect now" after a lost connection. */
  reconnect: () => void;
  /** "See the new one": follows the last submission of the problem if it is not the shown one.
   * Resolves to false when there is none. */
  showLatest: () => Promise<boolean>;
}

export function useSubmission({
  problem,
  version,
  difficulty,
  reconnectDelaysMs,
}: UseSubmissionOptions): SubmissionState {
  const queryClient = useQueryClient();
  const [store] = useState(
    () =>
      new SubmissionStore({
        eventsUrl,
        delays: reconnectDelaysMs,
        onFinalized: (id) =>
          void queryClient.invalidateQueries({ queryKey: submissionKeys.detail(id) }),
      }),
  );
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const check = snapshot.check?.problem === problem ? snapshot.check : null;
  const id = check?.id ?? null;
  const [quota, setQuota] = useState<Schemas["QuotaStatus"] | null>(null);

  useEffect(() => {
    store.attach(problem);
    return () => store.detach();
  }, [store, problem]);

  // A check that ended here or before the page opened; writing the same status again is a no-op.
  const finished = check !== null && isFinished(check) ? check : null;
  useEffect(() => {
    if (finished !== null) recordCheck({ ...finished, difficulty });
  }, [finished, difficulty]);

  // Not cached between visits: the last submission may have changed meanwhile.
  const latest = useQuery({
    queryKey: submissionKeys.latest(problem),
    queryFn: () => getLatest(problem),
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const detail = useQuery({
    queryKey: submissionKeys.detail(id ?? ""),
    queryFn: id === null ? skipToken : () => getSubmission(id),
    staleTime: Infinity,
  });

  const create = useMutation({
    mutationFn: async (input: StartInput) => {
      const { data, error } = await api.POST("/api/v1/submissions", {
        body: { problem, version, ...input },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: ({ quota: left, ...submission }) => {
      queryClient.setQueryData(submissionKeys.detail(submission.id), submission);
      if (left !== null) setQuota(left);
      store.start(submission);
    },
  });

  // A check being created wins over the last one.
  const creating = create.isPending;
  useEffect(() => {
    const found = latest.data?.submission;
    if (found != null && !creating && store.restore(found)) {
      queryClient.setQueryData(submissionKeys.detail(found.id), found);
    }
  }, [latest.data, creating, queryClient, store]);

  const cancel = useMutation({
    mutationFn: async (target: string) => {
      const { error } = await api.POST("/api/v1/submissions/{id}/cancel", {
        params: { path: { id: target } },
      });
      // A check that ended meanwhile: its `finalized` is on the way.
      if (error !== undefined && error.code !== "SUBMISSION_FINISHED") throw error;
    },
  });

  return {
    check,
    submission: detail.data ?? null,
    connection: check === null ? null : snapshot.connection,
    quota: quota ?? latest.data?.quota ?? null,
    restoring: check === null && latest.isPending,
    starting: create.isPending ? create.variables.kind : null,
    cancelling: cancel.isPending,
    cancelRequested: id !== null && cancel.variables === id,
    error: create.error ?? cancel.error,
    start: (input) => create.mutate(input),
    cancel: () => {
      if (id !== null) cancel.mutate(id);
    },
    reconnect: () => store.reconnect(),
    showLatest: async () => {
      const { data } = await latest.refetch();
      const found = data?.submission;
      if (found == null || found.id === id) return false;
      queryClient.setQueryData(submissionKeys.detail(found.id), found);
      store.start(found);
      return true;
    },
  };
}
