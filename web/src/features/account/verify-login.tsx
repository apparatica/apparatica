"use client";

// The page of a login link (FR-AUTH-05): the letter leads to `/login/email/verify#token=…`. The token
// is in the fragment, so link previews do not spend it; the page sends it to the API once and goes
// on to `next`. A full load rather than a soft navigation: the header, the guest banner and the
// cached data of the guest are rendered again for the user.
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle, Unlink } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { PageState } from "@/components/domain/page-state";
import { Button } from "@/components/ui/button";
import { asApiError } from "@/features/captcha/request";
import { ErrorState } from "@/features/errors/states";
import type { ApiError } from "@/lib/api/client";
import { sitePath } from "@/lib/session";

import { verifyLoginLink } from "./api";

/** The token of the fragment `#token=…`. */
export function linkToken(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token === null || token === "" ? null : token;
}

/** Goes to the page after the login; a seam for tests. */
export const navigation = { open: (path: string) => window.location.replace(path) };

export function VerifyLogin() {
  const t = useTranslations("login.verify");
  // undefined until the fragment is read: the server does not see it.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const verify = useMutation<Awaited<ReturnType<typeof verifyLoginLink>>, Error | ApiError, string>(
    {
      mutationFn: verifyLoginLink,
      onSuccess: (login) => navigation.open(sitePath(login.next) ?? "/"),
    },
  );
  const { mutate } = verify;
  const read = useRef(false);

  useEffect(() => {
    // Strict mode runs the effect twice: the fragment is read and the token spent once.
    if (read.current) return;
    read.current = true;
    const found = linkToken(window.location.hash);
    // The token leaves the address bar and the history at once.
    history.replaceState(history.state, "", window.location.pathname);
    setToken(found);
    if (found !== null) mutate(found);
  }, [mutate]);

  const failed = asApiError(verify.error);
  const invalid = token === null || failed?.code === "LOGIN_LINK_INVALID";
  if (invalid || failed?.code === "RATE_LIMITED" || failed?.code === "NOT_FOUND") {
    const key = invalid ? "invalid" : failed?.code === "RATE_LIMITED" ? "rateLimited" : "disabled";
    return (
      <PageState
        heading="h1"
        icon={Unlink}
        title={t(`${key}.title`)}
        description={t(`${key}.description`)}
        actions={
          <Button variant="primary" asChild>
            <Link href="/login">{t("again")}</Link>
          </Button>
        }
        className="py-16 sm:py-24"
      />
    );
  }
  if (verify.error !== null && token != null) {
    return <ErrorState error={verify.error} retry={() => verify.mutate(token)} />;
  }
  return (
    <section
      role="status"
      className="flex min-h-[300px] flex-col items-center justify-center gap-2.5 px-8 py-16 text-center sm:py-24"
    >
      <LoaderCircle size={32} aria-hidden="true" className="animate-spin text-mu" />
      <h1 className="text-[16px] leading-[1.5] font-semibold">{t("progress")}</h1>
    </section>
  );
}
