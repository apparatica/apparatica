"use client";

import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, WifiOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useCountdown } from "@/lib/clock";
import {
  checkNow,
  type Connectivity,
  dismissOffline,
  onReconnect,
  useConnectivity,
  useNetworkCardShown,
} from "@/lib/connectivity";

/** "Next attempt in 5 s.", or that a check runs now. */
export function NextCheck({ connectivity }: { connectivity: Connectivity & { state: "offline" } }) {
  const t = useTranslations("errors.network");
  const left = useCountdown(connectivity.nextAt, null);
  return left === null
    ? t("checking")
    : t("next", { seconds: Math.max(1, Math.ceil(left / 1000)) });
}

/** The strip under the header while the server does not answer (specs/08 §1): the code of the
 * guest stays in the browser, the connection is checked again by itself. Hidden while an error
 * card of the page shows the same, and after "Work offline" until the next loss. */
export function NetworkBanner() {
  const t = useTranslations("errors.network");
  const connectivity = useConnectivity();
  const covered = useNetworkCardShown();
  const queryClient = useQueryClient();

  // What failed while the connection was lost is read again.
  useEffect(
    () =>
      onReconnect(() => {
        void queryClient.invalidateQueries({
          predicate: (query) => query.state.status === "error",
        });
      }),
    [queryClient],
  );

  if (connectivity.state !== "offline" || connectivity.dismissed || covered) return null;
  return (
    <aside
      aria-label={t("label")}
      className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 border-b border-wn bg-wns px-4 py-2"
    >
      <WifiOff size={16} aria-hidden="true" className="flex-none text-wn" />
      <p className="min-w-0 flex-1">
        <span role="status" className="font-medium">
          {t("title")}.
        </span>{" "}
        {t("description")} <NextCheck connectivity={connectivity} />
      </p>
      <div className="flex flex-none gap-2">
        <Button onClick={checkNow}>
          <RefreshCw aria-hidden="true" />
          {t("retry")}
        </Button>
        <Button variant="ghost" onClick={dismissOffline}>
          {t("offline")}
        </Button>
      </div>
    </aside>
  );
}
