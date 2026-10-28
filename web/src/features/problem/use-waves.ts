"use client";

// The data of the waves tab: what the trace of the check is (waves-view.ts), its FST for the viewer,
// the recreation of an expired one (FR-WAV-05, POST /submissions/{id}/waveform) and the polling of
// the submission until the recreated FST is ready: it comes with no event (docs/api.md).
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getSubmission, submissionKeys } from "@/features/submission/api";
import type { Check, Submission } from "@/features/submission/machine";
import { apiUrl } from "@/lib/api/browser";
import { useConfig } from "@/lib/config";

import { type Artifact, type Trace, type WavesView, wavesView } from "./waves-view";

export const RECREATE_POLL_MS = 2000;
const MB = 1024 * 1024;

/** Where the FST of a trace downloads from: a redirect to a presigned URL of the storage. */
export function fstHref(trace: Trace): string {
  return apiUrl(
    `/api/v1/submissions/${encodeURIComponent(trace.submission)}/artifacts/fst?stage=${encodeURIComponent(trace.stage)}`,
  );
}

async function fetchFst(href: string): Promise<ArrayBuffer> {
  const response = await fetch(href);
  if (!response.ok) throw new Error(`FST: HTTP ${response.status}`);
  return response.arrayBuffer();
}

export interface UseWavesOptions {
  check: Check;
  /** The stored submission of the check (SubmissionState.submission). */
  submission: Submission | null;
  /** The viewer is wanted: the bytes are fetched only then. */
  wanted: boolean;
}

export function useWaves({ check, submission, wanted }: UseWavesOptions) {
  const queryClient = useQueryClient();
  const { data: config } = useConfig();
  const maxMb = config?.limits.waveforms.view_max_mb;
  const view: WavesView =
    maxMb === undefined ? { kind: "waiting" } : wavesView(check, submission, maxMb * MB);
  const trace = "trace" in view ? view.trace : null;

  // Shares the query of useSubmission; polls only while the FST is being recreated.
  const pending = view.kind === "pending";
  useQuery({
    queryKey: submissionKeys.detail(check.id),
    queryFn: () => getSubmission(check.id),
    enabled: pending,
    refetchInterval: pending ? RECREATE_POLL_MS : false,
  });

  const bytes = useQuery({
    queryKey: ["submissions", "fst", check.id, trace?.stage, trace?.artifact.size_bytes] as const,
    queryFn: wanted && view.kind === "ready" ? () => fetchFst(fstHref(view.trace)) : skipToken,
    staleTime: Infinity,
    gcTime: 60_000,
    retry: false,
  });

  const recreate = useMutation({
    mutationFn: async (target: Trace) => {
      const { data, error } = await api.POST("/api/v1/submissions/{id}/waveform", {
        params: { path: { id: target.submission } },
        body: { scope: "failure_window" },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: (artifact: Artifact, target) => {
      queryClient.setQueryData<Submission>(submissionKeys.detail(target.submission), (stored) =>
        stored === undefined
          ? stored
          : {
              ...stored,
              artifacts: stored.artifacts.map((item) =>
                item.kind === "fst" && item.stage === artifact.stage ? artifact : item,
              ),
            },
      );
    },
  });

  return { view, trace, bytes, recreate };
}
