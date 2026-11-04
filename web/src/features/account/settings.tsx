"use client";

// The settings of the account (specs/08 §1, no mock-up): the nick, changed once in 30 days, and the
// display name (FR-AUTH-02); logout on every device (FR-AUTH-04); the export of own data and the
// deletion of the account (FR-USR-05). A guest is asked to sign in. Logins of other providers join
// in Ф4.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, LogIn, LogOut } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, type ReactNode, useState } from "react";

import { PageState } from "@/components/domain/page-state";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { notify } from "@/components/ui/toast";
import { ErrorState } from "@/features/errors/states";
import type { ApiError, Schemas } from "@/lib/api/client";
import { saveFile } from "@/lib/download";

import { afterLogout, exportMe, logout, type Me, meKey, updateMe } from "./api";
import { DeleteAccount, useCancelDeletion, useDeletionDate } from "./deletion";
import { useMe } from "./use-me";

// Nick of the API (auth.schemas.Nick); the name is at most 60 characters.
const NICK = /^[a-z0-9_.-]{3,24}$/;
const NAME_MAX = 60;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-3 rounded-md border border-bd bg-sf px-4 py-3.5"
    >
      <h2 className="font-mono text-label text-mu uppercase">{title}</h2>
      {children}
    </section>
  );
}

export function SettingsPage() {
  const t = useTranslations("settings");
  const { data: me, error, refetch } = useMe();
  let body: ReactNode;
  if (error !== null) {
    body = <ErrorState error={error} retry={() => void refetch()} />;
  } else if (me === undefined) {
    body = <Skeleton className="h-64" />;
  } else if (me === null) {
    body = (
      <PageState
        icon={LogIn}
        title={t("guest.title")}
        description={t("guest.description")}
        actions={
          <Button variant="primary" asChild>
            <Link href="/login?next=/settings">{t("guest.login")}</Link>
          </Button>
        }
      />
    );
  } else {
    body = (
      <>
        <ProfileForm key={me.id} me={me} />
        <Sessions />
        <DataExport />
        <Deletion me={me} />
      </>
    );
  }
  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-4 px-4 pt-3 pb-4 sm:px-8 sm:pt-6">
      <div className="flex flex-col gap-0.5 max-sm:sr-only">
        <h1 className="text-title-1">{t("title")}</h1>
        <p className="text-mu">{t("subtitle")}</p>
      </div>
      {body}
    </div>
  );
}

function ProfileForm({ me }: { me: Me }) {
  const t = useTranslations("settings.profile");
  const format = useFormatter();
  const queryClient = useQueryClient();
  const [nick, setNick] = useState(me.nick);
  const [name, setName] = useState(me.display_name ?? "");
  const [nickError, setNickError] = useState<string | null>(null);
  const date = (at: string) =>
    format.dateTime(new Date(at), { day: "numeric", month: "long", year: "numeric" });

  const save = useMutation<Me, Error | ApiError, Schemas["MeUpdate"]>({
    mutationFn: updateMe,
    onSuccess: (updated) => {
      queryClient.setQueryData(meKey, updated);
      setNick(updated.nick);
      setName(updated.display_name ?? "");
      notify({ tone: "ok", title: t("saved") });
    },
    onError: (error) => {
      const code = "code" in error ? error.code : null;
      if (code === "NICK_TAKEN") {
        setNickError(t("nickTaken"));
      } else if (code === "NICK_CHANGE_TOO_SOON" && "params" in error) {
        const available = String(error.params?.["available_at"] ?? "");
        setNickError(t("nickTooSoon", { date: date(available) }));
        void queryClient.invalidateQueries({ queryKey: meKey });
      } else {
        notify({ tone: "er", title: t("saveFailed") });
      }
    },
  });

  const availableAt = me.nick_change_available_at;
  const changes: Schemas["MeUpdate"] = {};
  if (nick !== me.nick) changes.nick = nick;
  const trimmed = name.trim();
  if (trimmed !== (me.display_name ?? "")) changes.display_name = trimmed === "" ? null : trimmed;
  const changed = Object.keys(changes).length > 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (nick !== me.nick && !NICK.test(nick)) {
      setNickError(t("nickInvalid"));
      return;
    }
    setNickError(null);
    save.mutate(changes);
  };

  return (
    <Section title={t("title")}>
      <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
        <Field
          label={t("nick")}
          hint={availableAt === null ? t("nickHint") : t("nickLocked", { date: date(availableAt) })}
          error={nickError}
        >
          {(control) => (
            <Input
              {...control}
              value={nick}
              onChange={(event) => {
                setNick(event.target.value.toLowerCase());
                setNickError(null);
              }}
              disabled={availableAt !== null}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={24}
              className="font-mono sm:max-w-80"
            />
          )}
        </Field>
        <Field label={t("name")} hint={t("nameHint")}>
          {(control) => (
            <Input
              {...control}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="name"
              maxLength={NAME_MAX}
              className="sm:max-w-80"
            />
          )}
        </Field>
        {me.email !== null && (
          <div className="flex flex-col gap-[5px]">
            <span className="text-caption font-medium">{t("email")}</span>
            <span className="text-mu">{me.email}</span>
            <span className="text-[11.5px] text-mu">{t("emailHint")}</span>
          </div>
        )}
        <div>
          <Button type="submit" variant="primary" disabled={!changed} loading={save.isPending}>
            {t("save")}
          </Button>
        </div>
      </form>
    </Section>
  );
}

function Sessions() {
  const t = useTranslations("settings.sessions");
  const end = useMutation({
    mutationFn: () => logout(true),
    onSuccess: () => afterLogout.reload(),
    onError: () => notify({ tone: "er", title: t("failed") }),
  });
  return (
    <Section title={t("title")}>
      <p className="text-mu">{t("description")}</p>
      <div>
        <Button onClick={() => end.mutate()} loading={end.isPending}>
          <LogOut aria-hidden="true" />
          {t("logoutAll")}
        </Button>
      </div>
    </Section>
  );
}

function DataExport() {
  const t = useTranslations("settings.data");
  const download = useMutation({
    mutationFn: exportMe,
    onSuccess: ({ file, name }) => saveFile(file, name),
    onError: () => notify({ tone: "er", title: t("failed") }),
  });
  return (
    <Section title={t("title")}>
      <p className="text-mu">{t("description")}</p>
      <div>
        <Button onClick={() => download.mutate()} loading={download.isPending}>
          <Download aria-hidden="true" />
          {t("download")}
        </Button>
      </div>
    </Section>
  );
}

function Deletion({ me }: { me: Me }) {
  const t = useTranslations("settings.deletion");
  const date = useDeletionDate();
  const cancel = useCancelDeletion();
  return (
    <Section title={t("title")}>
      {me.delete_at === null ? (
        <>
          <p className="text-mu">{t("description")}</p>
          <DeleteAccount me={me} />
        </>
      ) : (
        <>
          <p>
            <span className="font-medium">{t("pending", { date: date(me.delete_at) })}</span>{" "}
            <span className="text-mu">{t("pendingHint")}</span>
          </p>
          <div>
            <Button onClick={() => cancel.mutate()} loading={cancel.isPending}>
              {t("cancel")}
            </Button>
          </div>
        </>
      )}
    </Section>
  );
}
