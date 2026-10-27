// The difficulty of a problem (components.md, "Сложность и теги"): three bars, the colour and the
// word. The levels come from GET /config (config/difficulties.yaml); their order fills the bars.
import type { ComponentProps } from "react";

import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export type Difficulty = Schemas["Difficulty"];

// The colour pair of a level by its `token`; Tailwind needs the class names written out. A token
// without a pair here is shown in the neutral colours.
const TONES: Record<string, string> = {
  e: "bg-es text-e",
  m: "bg-ms text-m",
  h: "bg-hs text-h",
};
const NEUTRAL = "bg-sf2 text-mu";
const BARS = ["h-1", "h-[7px]", "h-2.5"];

/** The colour pair of a level: `bg-*` and `text-*` classes. */
export const difficultyTone = (token: string): string => TONES[token] ?? NEUTRAL;

/** The level of a problem and its place among the levels of the config (from 1). */
export function findDifficulty(
  levels: readonly Difficulty[],
  key: string,
): { difficulty: Difficulty; rank: number } | undefined {
  const index = levels.findIndex((level) => level.key === key);
  const difficulty = levels[index];
  return difficulty && { difficulty, rank: index + 1 };
}

export type DifficultyBadgeProps = {
  difficulty: Difficulty;
  /** The place of the level in the config, from 1: as many bars are filled, at most three. */
  rank: number;
  /** 18 px high, without the bars: lists such as the command palette (sheet CmpD). */
  compact?: boolean;
} & Omit<ComponentProps<"span">, "children">;

export function DifficultyBadge({
  difficulty,
  rank,
  compact = false,
  className,
  ...props
}: DifficultyBadgeProps) {
  return (
    <span
      data-difficulty={difficulty.key}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-2 font-mono text-[11px] font-medium whitespace-nowrap",
        compact ? "h-[18px]" : "h-[22px]",
        difficultyTone(difficulty.token),
        className,
      )}
      {...props}
    >
      {!compact && (
        <span aria-hidden="true" className="inline-flex h-2.5 items-end gap-[1.5px]">
          {BARS.map((height, index) => (
            <i
              key={height}
              data-filled={index < rank || undefined}
              className={cn("block w-[2.5px] bg-current", height, index >= rank && "opacity-30")}
            />
          ))}
        </span>
      )}
      {difficulty.title}
    </span>
  );
}
