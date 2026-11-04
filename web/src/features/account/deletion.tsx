"use client";

// Deletion of the account (FR-USR-05): asked in the settings with the nick typed, done 7 days later;
// meanwhile the profile is hidden, a strip under the header of every page says when, and both it
// and the settings cancel it.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarX } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { notify } from "@/components/ui/toast";

import { deleteMe, type Me, meKey, restoreMe } from "./api";
import { useAccount } from "./session";

/** "11 ноября": the date is at most 7 days ahead. */
export function useDeletionDate(): (at: string) => string {
  const format = useFormatter();
  return (at) => format.dateTime(new Date(at), { day: "numeric", month: "long" });
}

export function useCancelDeletion() {
  const t = useTranslations("settings.deletion");
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: restoreMe,
    onSuccess: (me) => {
      queryClient.setQueryData(meKey, me);
      notify({ tone: "ok", title: t("cancelled") });
    },
    onError: () => notify({ tone: "er", title: t("cancelFailed") }),
  });
}

/** The strip under the header while the account waits for deletion. */
export function DeletionBanner() {
  const t = useTranslations("settings.deletion");
  const me = useAccount();
  const date = useDeletionDate();
  const cancel = useCancelDeletion();
  if (me?.delete_at == null) return null;
  return (
    <aside
      aria-label={t("banner")}
      className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 border-b border-wn bg-wns px-4 py-2"
    >
      <CalendarX size={16} aria-hidden="true" className="flex-none text-wn" />
      <p className="min-w-0 flex-1">
        <span className="font-medium">{t("pending", { date: date(me.delete_at) })}</span>{" "}
        {t("pendingHint")}
      </p>
      <Button className="flex-none" onClick={() => cancel.mutate()} loading={cancel.isPending}>
        {t("cancel")}
      </Button>
    </aside>
  );
}

/** «Удалить аккаунт»: a dialog that asks to type the nick. */
export function DeleteAccount({ me }: { me: Me }) {
  const t = useTranslations("settings.deletion");
  const date = useDeletionDate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [nick, setNick] = useState("");
  const ask = useMutation({
    mutationFn: deleteMe,
    onSuccess: (updated) => {
      queryClient.setQueryData(meKey, updated);
      setOpen(false);
      if (updated.delete_at !== null) {
        notify({ tone: "ok", title: t("asked", { date: date(updated.delete_at) }) });
      }
    },
    onError: () => notify({ tone: "er", title: t("failed") }),
  });
  const confirmed = nick.trim().toLowerCase() === me.nick;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (confirmed) ask.mutate();
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setNick("");
      }}
    >
      <div>
        <DialogTrigger asChild>
          <Button variant="danger">{t("delete")}</Button>
        </DialogTrigger>
      </div>
      <DialogContent>
        <form noValidate onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("dialogTitle")}</DialogTitle>
            <DialogDescription>{t("dialogDescription")}</DialogDescription>
          </DialogHeader>
          <DialogBody className="flex flex-col gap-3">
            <p>{t("dialogExport")}</p>
            <Field label={t("confirm", { nick: me.nick })}>
              {(control) => (
                <Input
                  {...control}
                  value={nick}
                  onChange={(event) => setNick(event.target.value)}
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  maxLength={24}
                  className="font-mono sm:max-w-80"
                />
              )}
            </Field>
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button">{t("keep")}</Button>
            </DialogClose>
            <Button type="submit" variant="danger" disabled={!confirmed} loading={ask.isPending}>
              {t("delete")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
