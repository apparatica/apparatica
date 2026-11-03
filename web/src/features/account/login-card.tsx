"use client";

// The card of the login page (FR-AUTH-01, mock-up Login): a button per enabled provider, the form
// of a login link (FR-AUTH-05) and, once it is sent, «Проверьте почту» in its place; the guest
// way and the consent line (FR-AUTH-06). A provider login is a navigation of the browser: its
// failure comes back as `?error=`.
import { useMutation } from "@tanstack/react-query";
import { ChevronRight, CircleAlert, CircleX, Info, Mail, MailCheck } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { type FormEvent, type ReactNode, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/toast";
import { CaptchaDialog } from "@/features/captcha/captcha-dialog";
import { asApiError, type CaptchaRequest, captchaRequest } from "@/features/captcha/request";
import type { ApiError, Schemas } from "@/lib/api/client";

import { requestLoginLink } from "./api";
import type { LoginPageProps } from "./login-page";

// The marks of the mock-up; a provider without one shows the start of its title.
const MARKS: Record<string, string> = {
  github: "GH",
  google: "G",
  telegram: "TG",
  vk: "VK",
  yandex: "Я",
};

// The callback errors of the API (docs/api.md, «Вход через провайдера»).
const LOGIN_ERRORS = ["access_denied", "invalid_state", "provider_error", "rate_limited"] as const;

function loginError(error: string): (typeof LOGIN_ERRORS)[number] | "unknown" {
  return LOGIN_ERRORS.find((known) => known === error) ?? "unknown";
}

// Enough to catch a typo; the API checks the address itself.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const strong = (chunks: ReactNode) => <strong className="font-medium text-tx">{chunks}</strong>;

// The legal documents (T2.5).
const legal = "underline underline-offset-2 hover:text-tx";
const terms = (chunks: ReactNode) => (
  <Link href="/legal/terms" className={legal}>
    {chunks}
  </Link>
);
const privacy = (chunks: ReactNode) => (
  <Link href="/legal/privacy" className={legal}>
    {chunks}
  </Link>
);

export function LoginCard({ providers, next, error }: LoginPageProps) {
  const t = useTranslations("login");
  const oauth = providers.filter((provider) => provider.kind === "oauth");
  const email = providers.some((provider) => provider.kind === "email");
  return (
    <section
      aria-labelledby="login-title"
      className="flex w-full max-w-[400px] flex-none flex-col gap-4 rounded-lg border border-bd bg-sf px-5 pt-6 pb-5 sm:px-7 sm:pt-7 sm:pb-6"
    >
      <div className="flex flex-col gap-1">
        <h1 id="login-title" className="text-[20px] leading-7 font-semibold tracking-[-0.01em]">
          {t("title")}
        </h1>
        <p className="text-mu">{t("subtitle")}</p>
      </div>
      {error !== null && (
        <div role="alert" className="flex gap-2.5 rounded-md bg-ers px-3 py-2.5">
          <CircleAlert size={16} aria-hidden="true" className="mt-0.5 flex-none text-er" />
          <p>{t(`errors.${loginError(error)}`)}</p>
        </div>
      )}
      {oauth.length > 0 && (
        <ul className="flex flex-col gap-2">
          {oauth.map((provider) => (
            <li key={provider.key}>
              <ProviderButton provider={provider} next={next} />
            </li>
          ))}
        </ul>
      )}
      {oauth.length > 0 && email && (
        <div className="flex items-center gap-2.5 text-caption text-mu">
          <span aria-hidden="true" className="h-px flex-1 bg-bd" />
          {t("orEmail")}
          <span aria-hidden="true" className="h-px flex-1 bg-bd" />
        </div>
      )}
      {email && <EmailLogin next={next} />}
      {providers.length === 0 && <p className="text-mu">{t("unavailable")}</p>}
      <div className="flex gap-2.5 rounded-md border border-bd bg-sf2 px-3 py-2.5">
        <Info size={14} aria-hidden="true" className="mt-[3px] flex-none text-mu" />
        <div className="flex flex-col gap-0.5 leading-[1.4]">
          <p>{t("guest")}</p>
          <Link
            href={next ?? "/problems"}
            className="self-start text-ac underline underline-offset-2"
          >
            {t("asGuest")}
          </Link>
        </div>
      </div>
      <p className="text-[11.5px] leading-normal text-mu">
        {t.rich("consent", { terms, privacy })}
      </p>
    </section>
  );
}

function ProviderButton({
  provider,
  next,
}: {
  provider: Schemas["AuthProvider"];
  next: string | null;
}) {
  const t = useTranslations("login");
  const query = next === null ? "" : `?${new URLSearchParams({ next }).toString()}`;
  return (
    // A navigation, not a request: the API redirects to the provider (docs/api.md).
    <a
      href={`/api/v1/auth/${encodeURIComponent(provider.key)}/login${query}`}
      className="flex h-10 w-full items-center gap-3 rounded-md border border-bc bg-sf px-3 text-[13px] hover:bg-sf2"
    >
      <span
        aria-hidden="true"
        className="flex size-[22px] flex-none items-center justify-center rounded-sm border border-bd bg-sf2 font-mono text-[10.5px] font-medium"
      >
        {MARKS[provider.key] ?? provider.title.slice(0, 2).toUpperCase()}
      </span>
      <span className="flex-1">{t("with", { provider: provider.title })}</span>
      <ChevronRight size={16} aria-hidden="true" className="flex-none text-mu" />
    </a>
  );
}

type Sent = { email: string } | null;

function EmailLogin({ next }: { next: string | null }) {
  const t = useTranslations("login.email");
  const id = useId();
  const [address, setAddress] = useState("");
  const [sent, setSent] = useState<Sent>(null);
  const [problem, setProblem] = useState<{ text: string; invalid: boolean } | null>(null);
  const [captcha, setCaptcha] = useState<CaptchaRequest | null>(null);

  const request = useMutation<unknown, Error | ApiError, Schemas["EmailLoginRequest"]>({
    mutationFn: requestLoginLink,
    onSuccess: (_, body) => {
      if (sent !== null) notify({ tone: "ok", title: t("resent") });
      setSent({ email: body.email });
      setProblem(null);
    },
    onError: (error) => {
      const found = asApiError(error);
      const asked = captchaRequest(error, Date.now());
      if (asked !== null) {
        setCaptcha(asked);
        return;
      }
      const text = problemText(found, t);
      if (sent !== null) notify({ tone: "er", title: text });
      else setProblem({ text, invalid: found?.status === 422 });
    },
  });
  const send = (email: string, solution: string | null = null) =>
    request.mutate({ email, next, ...(solution !== null && { captcha: solution }) });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const email = address.trim();
    if (!EMAIL.test(email)) {
      setProblem({ text: t("invalid"), invalid: true });
      return;
    }
    setProblem(null);
    send(email);
  };

  const dialog = (
    <CaptchaDialog
      purpose="login"
      request={captcha}
      onCancel={() => setCaptcha(null)}
      onSolve={(solution) => {
        setCaptcha(null);
        send(sent?.email ?? address.trim(), solution);
      }}
    />
  );

  if (sent !== null) {
    return (
      <div
        role="status"
        className="flex flex-col gap-3 rounded-md border border-bd bg-sf2 px-3.5 py-3"
      >
        <div className="flex gap-2.5">
          <MailCheck size={18} aria-hidden="true" className="mt-px flex-none text-ok" />
          <div className="flex flex-col gap-1">
            <h2 className="font-medium">{t("sentTitle")}</h2>
            <p className="text-mu">{t.rich("sentBody", { email: sent.email, strong })}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button loading={request.isPending} onClick={() => send(sent.email)}>
            {t("resend")}
          </Button>
          <Button variant="ghost" onClick={() => setSent(null)}>
            {t("another")}
          </Button>
        </div>
        {dialog}
      </div>
    );
  }

  const noteId = `${id}-note`;
  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-2">
      <div className="flex h-10 items-center gap-2 rounded-md border border-bc bg-ed px-3 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-1 has-[input:focus-visible]:outline-ac has-[[aria-invalid=true]]:border-er has-[[aria-invalid=true]]:shadow-[inset_0_0_0_1px_var(--er)]">
        <Mail size={14} aria-hidden="true" className="flex-none text-mu" />
        <input
          id={id}
          type="email"
          aria-label={t("label")}
          placeholder="name@example.com"
          autoComplete="email"
          spellCheck={false}
          value={address}
          onChange={(event) => {
            setAddress(event.target.value);
            setProblem(null);
          }}
          aria-describedby={problem !== null ? noteId : undefined}
          aria-invalid={problem?.invalid === true || undefined}
          className="h-full min-w-0 flex-1 bg-transparent text-[13px] outline-none! placeholder:text-mu"
        />
      </div>
      {problem !== null && (
        <p id={noteId} className="flex items-center gap-[5px] text-[11.5px] text-er">
          <CircleX size={14} aria-hidden="true" className="flex-none" />
          {problem.text}
        </p>
      )}
      <Button
        type="submit"
        variant="primary"
        loading={request.isPending}
        className="h-10 text-[13px]"
      >
        {t("submit")}
      </Button>
      {dialog}
    </form>
  );
}

function problemText(
  error: ApiError | null,
  t: ReturnType<typeof useTranslations<"login.email">>,
): string {
  if (error?.status === 422) return t("invalid");
  if (error?.code === "RATE_LIMITED") {
    const retry = error.params?.["retry_after_s"];
    return typeof retry === "number"
      ? t("rateLimitedFor", { minutes: Math.max(1, Math.ceil(retry / 60)) })
      : t("rateLimited");
  }
  if (error?.code === "NOT_FOUND") return t("disabled");
  return t("failed");
}
