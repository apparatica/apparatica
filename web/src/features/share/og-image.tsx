// OG pictures of problems and solutions (FR-SHR-02, components.md «OG-карточка», mock-up Og):
// 1200 × 630, always in the dark palette. Satori draws them on the server; it knows no CSS
// variables, so the colours are the hex values of the dark block of tokens.css, and the fonts are
// the IBM Plex files of @fontsource (Latin and Cyrillic; satori takes woff, not woff2). The code of
// a solution never gets here.
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";
import { getFormatter, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { isMetricName, metricOf, metricWords } from "@/features/leaderboard/metrics";

import type { ProblemCard, ShareCard, ShareLevel, SolutionCard } from "./card";

export const OG_SIZE = { width: 1200, height: 630 };

/** The dark block of tokens.css. */
const C = {
  sf: "#0d100e",
  sf2: "#151a17",
  bd: "#222a25",
  tx: "#dfe6df",
  mu: "#8f9b92",
  ac: "#22d3ee",
  acs: "#0b2a31",
  ok: "#4ade80",
};

/** The colour pairs of the levels by their token, as in DifficultyBadge. */
const LEVELS: Record<string, { fg: string; bg: string }> = {
  e: { fg: "#5eead4", bg: "#0d2b28" },
  m: { fg: "#79c0ff", bg: "#10233a" },
  h: { fg: "#c4b5fd", bg: "#221a3d" },
};
const NEUTRAL = { fg: C.mu, bg: C.sf2 };

// Satori takes the glyphs of a family from the font of the best weight only, so each subset is a
// family of its own and a style names both: Cyrillic first, Latin (digits, punctuation) after.
const SUBSETS = ["cyrillic", "latin"] as const;
const SANS_FAMILY = "Plex Sans";
const MONO_FAMILY = "Plex Mono";
const families = (name: string) => SUBSETS.map((subset) => `${name} ${subset}`).join(", ");
const SANS = families(SANS_FAMILY);
const MONO = families(MONO_FAMILY);

type Font = { name: string; data: Buffer; weight: 400 | 500 | 600; style: "normal" };

const FONT_FILES = [
  [SANS_FAMILY, "ibm-plex-sans", 400],
  [SANS_FAMILY, "ibm-plex-sans", 600],
  [MONO_FAMILY, "ibm-plex-mono", 400],
  [MONO_FAMILY, "ibm-plex-mono", 500],
] as const;

/** The files of the fonts; next.config.ts traces them into the standalone server. */
export const FONT_DIR = "node_modules/@fontsource";

let fonts: Promise<Font[]> | null = null;

/** Read once per process; a failed read is tried again by the next picture. */
function loadFonts(): Promise<Font[]> {
  fonts ??= Promise.all(
    FONT_FILES.flatMap(([name, family, weight]) =>
      SUBSETS.map(async (subset) => ({
        name: `${name} ${subset}`,
        weight,
        style: "normal" as const,
        data: await readFile(
          join(
            process.cwd(),
            FONT_DIR,
            family,
            "files",
            `${family}-${subset}-${weight}-normal.woff`,
          ),
        ),
      })),
    ),
  ).catch((error: unknown) => {
    fonts = null;
    throw error;
  });
  return fonts;
}

function Logo() {
  return (
    <svg
      width="44"
      height="44"
      viewBox="0 0 24 24"
      fill="none"
      stroke={C.ac}
      strokeWidth="2"
      strokeLinejoin="round"
    >
      <rect x="4" y="3" width="17" height="18" rx="2" />
      <path d="M4 9.5l5 2.5-5 2.5" />
    </svg>
  );
}

/** Three signals in the top right corner: two clocks and a bus. */
function Waves() {
  return (
    <svg
      width="520"
      height="150"
      viewBox="0 0 520 150"
      fill="none"
      strokeWidth="2"
      style={{ position: "absolute", top: 28, right: 0 }}
    >
      <path d="M0 32h70V2h80v30h80V2h80v30h80V2h80v30h50" stroke={C.ac} strokeOpacity="0.55" />
      <path d="M0 80h110V50h80v30h140V50h80v30h110" stroke={C.ac} strokeOpacity="0.4" />
      <path
        d="M0 130h40l15-25h120l15 25h160l15-25h120l15 25h20"
        stroke={C.ac}
        strokeOpacity="0.25"
      />
    </svg>
  );
}

function Level({ level }: { level: ShareLevel }) {
  const { fg, bg } = LEVELS[level.difficulty.token] ?? NEUTRAL;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        height: 44,
        padding: "0 16px",
        borderRadius: 4,
        background: bg,
        color: fg,
        fontFamily: MONO,
        fontSize: 24,
        fontWeight: 500,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 20 }}>
        {[8, 14, 20].map((height, index) => (
          <div
            key={height}
            style={{
              width: 5,
              height,
              background: fg,
              opacity: index < level.rank ? 1 : 0.3,
            }}
          />
        ))}
      </div>
      {level.difficulty.title}
    </div>
  );
}

function Accepted({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, color: C.ok, fontSize: 26 }}>
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={C.ok} strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {text}
    </div>
  );
}

function Arrow() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke={C.mu} strokeWidth="2">
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A figure of the bottom row: a caption over a big mono number with its unit. */
function Figure({
  label,
  value,
  unit,
  accent = false,
  align = "flex-start",
}: {
  label: string;
  /** A string: satori wants `display: flex` on a div with any other child, a number too. */
  value: string;
  unit?: string | null;
  accent?: boolean;
  align?: "flex-start" | "flex-end";
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: align, gap: 6 }}>
      <div style={{ fontSize: 22, color: C.mu }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <div style={{ fontFamily: MONO, fontSize: 54, color: accent ? C.ac : C.tx }}>{value}</div>
        {unit != null && <div style={{ fontFamily: MONO, fontSize: 24, color: C.mu }}>{unit}</div>}
      </div>
    </div>
  );
}

function Frame({
  badges,
  title,
  subtitle,
  bottom,
}: {
  badges: ReactNode;
  title: string;
  subtitle: ReactNode;
  bottom: ReactNode;
}) {
  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        width: "100%",
        height: "100%",
        padding: "56px 64px 48px",
        background: `radial-gradient(circle at 100% 0%, ${C.acs} 0%, ${C.sf} 45%)`,
        color: C.tx,
        fontFamily: SANS,
      }}
    >
      <Waves />
      <div
        style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 32, fontWeight: 600 }}
      >
        <Logo />
        Apparatica
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 64 }}>{badges}</div>
      <div
        style={{
          marginTop: 22,
          fontSize: 84,
          fontWeight: 600,
          lineHeight: 1.1,
          letterSpacing: "-0.01em",
          lineClamp: 1,
        }}
      >
        {title}
      </div>
      <div style={{ display: "flex", marginTop: 18, fontSize: 28, color: C.mu }}>{subtitle}</div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginTop: "auto",
          paddingTop: 28,
          borderTop: `1px solid ${C.bd}`,
        }}
      >
        {bottom}
      </div>
    </div>
  );
}

async function ProblemOg({ card }: { card: ProblemCard }) {
  const t = await getTranslations("share.og");
  const words = metricWords(await getTranslations("leaderboard"), await getFormatter());
  const format = await getFormatter();
  return (
    <Frame
      badges={card.level !== null && <Level level={card.level} />}
      title={card.title}
      subtitle={card.tags.join(" · ")}
      bottom={
        <div style={{ display: "flex", gap: 72 }}>
          <Figure
            label={t("acceptance")}
            value={
              card.acceptance === null
                ? "—"
                : format.number(card.acceptance, { style: "percent", maximumFractionDigits: 0 })
            }
          />
          {card.order.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ fontSize: 22, color: C.mu }}>{t("order")}</div>
              <div
                style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 44, height: 72 }}
              >
                {card.order.flatMap(({ metric }, index) => [
                  ...(index > 0 ? [<Arrow key={`arrow-${metric}`} />] : []),
                  <span key={metric}>{words.name(metric)}</span>,
                ])}
              </div>
            </div>
          )}
        </div>
      }
    />
  );
}

async function SolutionOg({ card }: { card: SolutionCard }) {
  const t = await getTranslations("share.og");
  const verdict = await getTranslations("solution.verdict");
  const names = await getTranslations("leaderboard");
  const words = metricWords(names, await getFormatter());
  const main = card.main === null ? null : metricOf(card.main);
  const by = main !== null && isMetricName(main) ? names(`by.${main}`).toLowerCase() : null;
  const { placement } = card;
  let place: string | null = null;
  if (placement !== null) {
    place = by === null ? t("place", placement) : t("placeBy", { ...placement, by });
  }
  return (
    <Frame
      badges={[
        card.level !== null && <Level key="level" level={card.level} />,
        <Accepted
          key="verdict"
          text={card.status === "accepted" ? verdict("accepted") : verdict("acceptedWarnings")}
        />,
      ]}
      title={card.title}
      subtitle={[
        <span key="solution">{t("solution")}&nbsp;</span>,
        <span key="nick" style={{ color: C.tx }}>
          {card.nick}
        </span>,
        place !== null && <span key="place">&nbsp;·&nbsp;{place}</span>,
      ]}
      bottom={[
        <div key="metrics" style={{ display: "flex", gap: 52 }}>
          {card.metrics.map(({ key, value }) => (
            <Figure
              key={key}
              label={words.name(key)}
              value={words.value(key, value)}
              unit={words.unit(key)}
            />
          ))}
        </div>,
        placement !== null && (
          <Figure
            key="rank"
            label={t("rank")}
            value={String(placement.rank)}
            unit={t("of", { total: placement.total })}
            accent
            align="flex-end"
          />
        ),
      ]}
    />
  );
}

/** The picture of a card; cached by the routes that serve it. */
export async function renderOg(card: ShareCard): Promise<ImageResponse> {
  const element = card.kind === "problem" ? await ProblemOg({ card }) : await SolutionOg({ card });
  return new ImageResponse(element, { ...OG_SIZE, fonts: await loadFonts() });
}
