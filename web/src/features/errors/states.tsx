"use client";

// The error pages of sheet PageErrors (specs/08 §1): a missing page or problem (404), a failure of
// the page (500) and a lost connection. The empty catalogue is the fourth state of the sheet
// (features/catalog).
import { OctagonAlert, RefreshCw, SearchX, WifiOff } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { PageState } from "@/components/domain/page-state";
import { NextCheck } from "@/components/shell/network-banner";
import { Button } from "@/components/ui/button";
import {
  checkNow,
  claimNetworkCard,
  type Connectivity,
  onReconnect,
  useConnectivity,
} from "@/lib/connectivity";

// Error pages stand in the middle of the window, below the header.
const PAGE = "py-16 sm:py-24";

/** 404: the address leads nowhere; for a problem page, the problem is not published. */
export function NotFoundState({ kind = "page" }: { kind?: "page" | "problem" }) {
  const t = useTranslations("errors");
  const path = usePathname();
  const key = kind === "problem" ? "problemNotFound" : "notFound";
  return (
    <PageState
      heading="h1"
      icon={SearchX}
      title={t(`${key}.title`)}
      description={t(`${key}.description`)}
      code={t("notFound.code", { path })}
      actions={
        <Button variant="primary" asChild>
          <Link href="/problems">{t("notFound.toCatalog")}</Link>
        </Button>
      }
      className={PAGE}
    />
  );
}

/** 500: the page failed; `digest` finds the error in the logs of the server. */
export function ServerErrorState({
  digest,
  onRefresh,
}: {
  digest: string | null;
  onRefresh: () => void;
}) {
  const t = useTranslations("errors.server");
  return (
    <PageState
      heading="h1"
      icon={OctagonAlert}
      title={t("title")}
      description={t("description")}
      code={digest === null ? t("code") : t("codeId", { id: digest })}
      actions={
        <Button variant="primary" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          {t("refresh")}
        </Button>
      }
      className={PAGE}
    />
  );
}

/** The page could not load without the server: it loads again once the server answers. */
export function NetworkErrorState({
  connectivity,
  onRetry,
}: {
  connectivity: Connectivity & { state: "offline" };
  onRetry: () => void;
}) {
  const t = useTranslations("errors.network");
  return (
    <PageState
      heading="h1"
      icon={WifiOff}
      title={t("title")}
      description={
        <>
          {t("description")} <NextCheck connectivity={connectivity} />
        </>
      }
      code={t("code", { attempt: connectivity.attempt })}
      actions={
        <Button variant="primary" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          {t("retry")}
        </Button>
      }
      className={PAGE}
    />
  );
}

function digestOf(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("digest" in error)) return null;
  return typeof error.digest === "string" ? error.digest : null;
}

/** The fallback of an error boundary: without a connection, the network card that loads the page
 * again when the server answers; else the failure of the page, refreshed as a whole (a chunk of an
 * older build is gone after a deploy, so a retry of the segment alone is not enough). */
export function ErrorState({ error, retry }: { error: unknown; retry: () => void }) {
  const connectivity = useConnectivity();
  const offline = connectivity.state === "offline";

  useEffect(() => {
    if (!offline) return;
    const release = claimNetworkCard();
    const unsubscribe = onReconnect(retry);
    return () => {
      release();
      unsubscribe();
    };
  }, [offline, retry]);

  if (connectivity.state === "offline") {
    return <NetworkErrorState connectivity={connectivity} onRetry={checkNow} />;
  }
  return <ServerErrorState digest={digestOf(error)} onRefresh={() => location.reload()} />;
}
