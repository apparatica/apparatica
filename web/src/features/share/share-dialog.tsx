"use client";

// «Поделиться» (FR-SHR-01, mock-up ModalsA): how the link will look in messages, the link with
// «Копировать», and VK, Telegram and X. A problem is shared by its page, a solution by its short
// link `/s/…`. The address of the site is the one the visitor opened it at. The card is drawn
// with the tokens of the theme; the OG picture behind it is always dark (specs/08 §6).
import { Copy, Share2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";

import { DifficultyBadge } from "@/components/domain/difficulty-badge";
import { Logo } from "@/components/shell/logo";
import { Button, type ButtonProps } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { notify } from "@/components/ui/toast";
import { metricOf, useMetricWords } from "@/features/leaderboard/metrics";
import { copyLink } from "@/lib/share";

import type { ProblemCard, ShareCard, SolutionCard } from "./card";

export interface ShareProps {
  card: ShareCard;
  /** The path of the shared page: `/problems/…` or `/s/…`. */
  href: string;
}

/** The text that goes with the link to VK, Telegram and X. */
function useShareText(card: ShareCard): string {
  const t = useTranslations("share.text");
  if (card.kind === "problem") return t("problem", { title: card.title });
  const { title, nick, placement } = card;
  return placement === null
    ? t("solution", { title, nick })
    : t("solutionPlace", { title, nick, ...placement });
}

/** Where the networks take a link: their pages of a new post. */
export function networkLinks(url: string, text: string) {
  const u = encodeURIComponent(url);
  const x = encodeURIComponent(text);
  return {
    vk: `https://vk.com/share.php?url=${u}&title=${x}`,
    telegram: `https://t.me/share/url?url=${u}&text=${x}`,
    x: `https://x.com/intent/post?url=${u}&text=${x}`,
  };
}

function ProblemFoot({ card }: { card: ProblemCard }) {
  const t = useTranslations("share.card");
  return (
    <>
      <span className="min-w-0 truncate text-mu">{card.tags.join(" · ")}</span>
      {card.acceptance !== null && (
        <span className="flex-none font-mono text-label text-mu">
          {t("acceptance", { percent: `${Math.round(card.acceptance * 100)}%` })}
        </span>
      )}
    </>
  );
}

function SolutionFoot({ card }: { card: SolutionCard }) {
  const t = useTranslations("share.card");
  const words = useMetricWords();
  // Counts take their noun by the number: «176 ячеек».
  const noun = (key: string, value: number) => {
    const metric = metricOf(key);
    return metric === "cells" || metric === "flops"
      ? t(`noun.${metric}`, { count: value })
      : words.name(key);
  };
  return (
    <>
      <span className="flex min-w-0 flex-wrap gap-x-3.5 font-mono text-label">
        {card.metrics.map(({ key, value }) => {
          const unit = words.unit(key);
          return (
            <span key={key}>
              <span className="font-medium text-tx">{words.value(key, value)}</span>
              <span className="text-mu"> {unit ?? noun(key, value)}</span>
            </span>
          );
        })}
      </span>
      <span className="flex-none font-mono text-label text-mu">
        {card.placement !== null && <>{t("place", card.placement)} · </>}
        {card.nick}
      </span>
    </>
  );
}

/** The card of the link as a messenger shows it: a small copy of the OG picture. */
export function SharePreview({ card }: { card: ShareCard }) {
  const t = useTranslations("shell");
  return (
    <div
      data-testid="share-preview"
      className="flex flex-col gap-2.5 rounded-md border border-bd bg-ed p-3.5"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-caption font-semibold">
          <Logo size={14} />
          {t("brand")}
        </span>
        {card.level !== null && (
          <DifficultyBadge difficulty={card.level.difficulty} rank={card.level.rank} compact />
        )}
      </div>
      <p className="truncate text-[16px] leading-6 font-semibold">{card.title}</p>
      <div className="flex items-baseline justify-between gap-3 text-caption">
        {card.kind === "problem" ? <ProblemFoot card={card} /> : <SolutionFoot card={card} />}
      </div>
    </div>
  );
}

/** The body of the open dialog: Radix mounts it only then, so always in the browser. */
function ShareBody({ card, href }: ShareProps) {
  const t = useTranslations("share");
  const id = useId();
  const text = useShareText(card);
  const url = new URL(href, window.location.origin).toString();
  const links = networkLinks(url, text);
  const copy = async () => {
    if ((await copyLink(url)) === "copied") notify({ tone: "ok", title: t("copied") });
    else notify({ tone: "er", title: t("copyFailed") });
  };
  const network = (key: keyof typeof links, mark: string) => (
    <Button asChild className="justify-start">
      <a href={links[key]} target="_blank" rel="noopener noreferrer">
        <span aria-hidden="true" className="font-mono text-label text-mu">
          {mark}
        </span>
        {t(key)}
      </a>
    </Button>
  );
  return (
    <DialogBody className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <DialogDescription className="text-caption">{t("preview")}</DialogDescription>
        <SharePreview card={card} />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={id} className="text-caption text-mu">
          {t(`link.${card.kind}`)}
        </label>
        <div className="flex gap-2">
          <Input
            id={id}
            readOnly
            value={url}
            className="font-mono"
            onFocus={(event) => event.currentTarget.select()}
          />
          <Button variant="outline" onClick={() => void copy()}>
            <Copy aria-hidden="true" />
            {t("copy")}
          </Button>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {network("vk", "VK")}
        {network("telegram", "TG")}
        {network("x", "X")}
      </div>
    </DialogBody>
  );
}

function ShareContent({ card, href }: ShareProps) {
  const t = useTranslations("share");
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{t(`title.${card.kind}`)}</DialogTitle>
      </DialogHeader>
      <ShareBody card={card} href={href} />
    </DialogContent>
  );
}

export type ShareButtonProps = ShareProps &
  Pick<ButtonProps, "variant" | "className"> & {
    /** Only the icon, with the label for screen readers (the header of the statement). */
    iconOnly?: boolean;
    children?: ReactNode;
  };

/** «Поделиться» that opens the dialog. */
export function ShareButton({
  card,
  href,
  variant,
  className,
  iconOnly = false,
  children,
}: ShareButtonProps) {
  const t = useTranslations("share");
  return (
    <Dialog>
      <DialogTrigger asChild>
        {iconOnly ? (
          <Button
            variant={variant ?? "ghost"}
            size="icon"
            aria-label={t(`title.${card.kind}`)}
            title={t(`title.${card.kind}`)}
            className={className}
          >
            <Share2 aria-hidden="true" />
          </Button>
        ) : (
          <Button variant={variant} className={className}>
            {children ?? (
              <>
                <Share2 aria-hidden="true" />
                {t("button")}
              </>
            )}
          </Button>
        )}
      </DialogTrigger>
      <ShareContent card={card} href={href} />
    </Dialog>
  );
}
