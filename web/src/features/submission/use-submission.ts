"use client";

// useSubmission: the check of a problem page (docs/frontend.md#проверка-usesubmission). Run and
// Submit create a submission, its event stream feeds the state, a dropped stream reconnects; an
// opened page restores the last submission of the problem and reads its stream to the end. A
// finished check goes to the local history of the guest (the catalogue shows it). An unfinished
// check goes on in the background when the page closes; it and a check that ends in a hidden tab
// are told about by a notice (FR-RUN-08).
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";

import { recordCheck } from "@/features/guest/history";
import { rememberSubmissions } from "@/features/guest/submissions";
import type { ApiError, Schemas } from "@/lib/api/client";

import { api, eventsUrl, getQuota, getRecent, getSubmission, submissionKeys } from "./api";
import { followInBackground, stopBackground } from "./background";
import { announceFinished } from "./finished";
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
  /** The title of the problem, for the notices. */
  title: string;
  /** The level of the problem, for the local history. */
  difficulty: string;
  /** The page was opened for this submission (`?submission=`): it is restored, not the last one. */
  wanted?: string | null | undefined;
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
  /** When the last start failed, `Date.now()` time: the waits of 429 and 428 count from it. */
  failedAt: number | null;
  start: (input: StartInput) => void;
  cancel: () => void;
  /** "Connect now" after a lost connection. */
  reconnect: () => void;
  /** Reads the quotas again, e.g. when a spent one should be back. */
  refreshQuota: () => void;
  /** "See the new one": follows the last submission of the problem if it is not the shown one.
   * Resolves to false when there is none. */
  showLatest: () => Promise<boolean>;
  /** Shows a submission of the problem from the list: its results, its stream. The shown one
   * stays as it is. */
  show: (submission: Submission) => void;
}

export function useSubmission({
  problem,
  version,
  title,
  difficulty,
  wanted = null,
  reconnectDelaysMs,
}: UseSubmissionOptions): SubmissionState {
  const queryClient = useQueryClient();
  const [store] = useState(
    () =>
      new SubmissionStore({
        eventsUrl,
        delays: reconnectDelaysMs,
        onFinalized: ({ id, kind, status }) => {
          void queryClient.invalidateQueries({ queryKey: submissionKeys.detail(id) });
          if (document.visibilityState === "hidden") {
            announceFinished({ id, problem, title, kind, status }, false);
          }
        },
      }),
  );
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const check = snapshot.check?.problem === problem ? snapshot.check : null;
  const id = check?.id ?? null;
  const [quota, setQuota] = useState<Schemas["QuotaStatus"] | null>(null);
  const [failedAt, setFailedAt] = useState<number | null>(null);

  // The page takes its check back from the background, and leaves an unfinished one there.
  useEffect(() => {
    stopBackground(problem);
    store.attach(problem);
    return () => {
      const { check: left } = store.getSnapshot();
      store.detach();
      if (left?.problem === problem && !isFinished(left)) {
        followInBackground({ check: left, title, difficulty });
      }
    };
  }, [store, problem, title, difficulty]);

  // A check that ended here or before the page opened; writing the same status again is a no-op.
  const finished = check !== null && isFinished(check) ? check : null;
  useEffect(() => {
    if (finished !== null) recordCheck({ ...finished, difficulty });
  }, [finished, difficulty]);

  // Not cached between visits: the last submission may have changed meanwhile. The query also
  // brings the local history up to date with the server.
  const [opened] = useState(wanted);
  const latest = useQuery({
    queryKey: submissionKeys.recent(problem, opened),
    queryFn: () => getRecent(problem, opened),
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const detail = useQuery({
    queryKey: submissionKeys.detail(id ?? ""),
    queryFn: id === null ? skipToken : () => getSubmission(id),
    staleTime: Infinity,
  });

  // The shown submission goes to the local history with the status of its live check: queued,
  // running, then the verdict of `finalized`.
  const shown = detail.data;
  const live = check?.id === shown?.id ? check : null;
  const status = live?.status;
  const verdict = live?.verdict;
  useEffect(() => {
    if (shown === undefined) return;
    rememberSubmissions([
      { ...shown, status: status ?? shown.status, verdict_detail: verdict ?? shown.verdict_detail },
    ]);
  }, [shown, status, verdict]);

  const follow = (found: Submission) => {
    queryClient.setQueryData(submissionKeys.detail(found.id), found);
    store.start(found);
  };

  const refreshQuota = () => {
    getQuota().then(
      (left) => {
        if (left !== null) setQuota(left);
      },
      () => {}, // the old value stays until the next response
    );
  };

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
    onError: (error) => {
      setFailedAt(Date.now());
      // Spent elsewhere (another tab): the counter catches up.
      if ("code" in error && error.code === "RATE_LIMITED") refreshQuota();
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
    failedAt: create.error === null ? null : failedAt,
    start: (input) => create.mutate(input),
    cancel: () => {
      if (id !== null) cancel.mutate(id);
    },
    reconnect: () => store.reconnect(),
    refreshQuota,
    showLatest: async () => {
      const found = (await getRecent(problem)).submission;
      if (found === null || found.id === id) return false;
      follow(found);
      return true;
    },
    show: (found) => {
      if (found.id !== id) follow(found);
    },
  };
}
