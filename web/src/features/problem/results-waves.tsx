"use client";

// The waves tab of the results (FR-WAV-01..06, sheet CmpC, mock-up BenchWave): the trace of the
// failed test in Surfer, in an isolated frame on the origin of the viewer (ADR-0004). The frame is
// made once the waves are wanted (a test failed or the tab was opened) and stays for later checks.
import { Crosshair, Download, Maximize2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useSyncExternalStore } from "react";

import { useFileSize } from "@/components/domain/duration";
import {
  DownloadFst,
  WaveformPanel,
  type WaveformPanelState,
} from "@/components/domain/waveform-panel";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { useResolvedTheme } from "@/components/shell/theme";
import type { Check } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import type { TraceView, Viewer } from "@/features/waveview/viewer";
import type { ApiError } from "@/lib/api/client";

import { fstHref, useWaves } from "./use-waves";
import { type Ports, signalItems, type Trace } from "./waves-view";

export interface ResultsWavesProps {
  check: Check;
  submission: SubmissionState;
  ports: Ports;
  viewer: Viewer;
  /** Make the frame of the viewer: the waves were wanted once. */
  wanted: boolean;
}

const traceKey = (trace: Trace) =>
  `${trace.submission}:${trace.stage}:${String(trace.artifact.size_bytes)}`;

function useRecreateFailure(): (error: Error | ApiError) => void {
  const t = useTranslations("problem.results.waves");
  return (error) => {
    let description = "detail" in error ? error.detail : error.message;
    if (
      "params" in error &&
      error.code === "RATE_LIMITED" &&
      error.params?.["quota"] === "waveforms"
    ) {
      const { limit, retry_after_s: retry } = error.params as {
        limit: number;
        retry_after_s: number;
      };
      description = t("quotaSpent", { limit, minutes: Math.max(1, Math.ceil(retry / 60)) });
    }
    notify({ tone: "er", title: t("recreateFailed"), description });
  };
}

/** The isolated frame of the viewer: scripts only, an opaque origin, no referrer (ADR-0004). */
function ViewerFrame({ viewer, src, title }: { viewer: Viewer; src: string; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const element = frame.current;
    if (element === null) return;
    viewer.attach(element);
    return () => viewer.detach(element);
  }, [viewer]);
  return (
    <iframe
      ref={frame}
      src={src}
      title={title}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      className="block size-full border-0"
    />
  );
}

export function ResultsWaves({ check, submission, ports, viewer, wanted }: ResultsWavesProps) {
  const t = useTranslations("problem.results.waves");
  const fileSize = useFileSize();
  const theme = useResolvedTheme();
  const recreateFailed = useRecreateFailure();
  const snapshot = useSyncExternalStore(viewer.subscribe, viewer.getSnapshot, viewer.getSnapshot);
  const { view, trace, bytes, recreate } = useWaves({
    check,
    submission: submission.submission,
    wanted,
  });

  useEffect(() => viewer.setTheme(`apparatica-${theme}`), [viewer, theme]);

  const data = bytes.data;
  const shown: TraceView | null =
    view.kind === "ready" && data !== undefined
      ? {
          key: traceKey(view.trace),
          bytes: data,
          signals: signalItems(view.trace.waveform, ports, (port) => t("expected", { port })),
          cursor:
            view.trace.waveform.cursor_time_ps === null
              ? null
              : {
                  time: view.trace.waveform.cursor_time_ps,
                  marker: t("marker", { cycle: view.trace.waveform.cursor_cycle ?? 0 }),
                },
        }
      : null;
  // Every render: the same trace again is a no-op of the viewer.
  useEffect(() => viewer.show(shown));

  const recreateTrace = (target: Trace) =>
    recreate.mutate(target, { onError: (error) => recreateFailed(error) });

  const state = ((): WaveformPanelState => {
    const viewerState = snapshot.state;
    switch (view.kind) {
      case "none":
        return { kind: "empty", caption: t(`none.${view.reason}`) };
      case "waiting":
        return { kind: "loading" };
      case "expired": {
        const limit = submission.quota?.waveforms.limit;
        return {
          kind: "empty",
          title: t("expired"),
          caption:
            limit === undefined ? t("expiredCaptionNoLimit") : t("expiredCaption", { limit }),
          action: (
            <Button loading={recreate.isPending} onClick={() => recreateTrace(view.trace)}>
              {t("recreate")}
            </Button>
          ),
        };
      }
      case "pending":
        return { kind: "loading", caption: t("pending") };
      case "failed":
        return {
          kind: "error",
          title: t("failed"),
          caption: t("failedCaption"),
          onRetry: () => recreateTrace(view.trace),
          retrying: recreate.isPending,
        };
      case "noViewer":
        return {
          kind: "empty",
          title: t("noViewer"),
          caption: t("noViewerCaption"),
          action: <DownloadFst href={fstHref(view.trace)} />,
        };
      case "tooBig":
        return {
          kind: "tooBig",
          size: fileSize(view.sizeBytes),
          downloadHref: fstHref(view.trace),
        };
      case "ready":
        if (bytes.isError) return { kind: "error", onRetry: () => void bytes.refetch() };
        if (viewerState.phase === "failed") {
          return { kind: "error", caption: t("viewerFailed"), onRetry: () => viewer.retry() };
        }
        if (viewerState.phase === "shown" && viewerState.key === traceKey(view.trace)) {
          return { kind: "normal" };
        }
        return { kind: "loading" };
    }
  })();

  const waveform = trace?.waveform;
  const size = trace?.artifact.size_bytes;
  const viewerUrl = submission.submission?.waveview_url ?? null;
  return (
    <WaveformPanel
      state={state}
      title={
        waveform === undefined
          ? undefined
          : t("title", { from: waveform.from_cycle, to: waveform.to_cycle })
      }
      info={
        waveform === undefined || size == null
          ? undefined
          : t("info", {
              cycles: waveform.to_cycle - waveform.from_cycle + 1,
              size: fileSize(size),
            })
      }
      tools={
        trace !== null && (
          <>
            <Tooltip content={t("toMismatch")}>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("toMismatch")}
                className="h-6 w-6"
                onClick={() => viewer.focus()}
              >
                <Crosshair aria-hidden="true" />
              </Button>
            </Tooltip>
            <Tooltip content={t("fit")}>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("fit")}
                className="h-6 w-6"
                onClick={() => viewer.fit()}
              >
                <Maximize2 aria-hidden="true" />
              </Button>
            </Tooltip>
            <Tooltip content={t("download")}>
              <Button variant="ghost" size="icon" className="h-6 w-6" asChild>
                <a href={fstHref(trace)} download aria-label={t("download")}>
                  <Download aria-hidden="true" />
                </a>
              </Button>
            </Tooltip>
          </>
        )
      }
    >
      {wanted && viewerUrl !== null && (
        <ViewerFrame
          key={`${snapshot.frame}:${viewerUrl}`}
          viewer={viewer}
          src={viewerUrl}
          title={t("frame")}
        />
      )}
    </WaveformPanel>
  );
}
