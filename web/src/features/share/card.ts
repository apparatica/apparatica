// What a card of a link shows (FR-SHR-01/02, mock-ups Og and ModalsA): the OG picture rendered by
// the server and its small copy in the dialog «Поделиться» are drawn from the same data.
import type { Difficulty } from "@/components/domain/difficulty-badge";
import { CARD_METRICS } from "@/features/leaderboard/metrics";
import type { Schemas } from "@/lib/api/client";

export interface ShareLevel {
  difficulty: Difficulty;
  /** The place of the level in the config, from 1: the filled bars. */
  rank: number;
}

/** A metric of the synthesis: `<stage key>.<metric>` and its value. */
export interface ShareMetric {
  key: string;
  value: number;
}

export interface ProblemCard {
  kind: "problem";
  title: string;
  level: ShareLevel | null;
  /** Titles of the tags. */
  tags: string[];
  /** The share of accepted Submits, 0…1; null before the first one. */
  acceptance: number | null;
  /** The formula of the leaderboard; empty without one. */
  order: Schemas["LeaderboardKey"][];
}

export interface SolutionCard {
  kind: "solution";
  title: string;
  level: ShareLevel | null;
  nick: string;
  status: "accepted" | "accepted_with_warnings";
  metrics: ShareMetric[];
  placement: { rank: number; total: number } | null;
  /** The first metric of the formula: «по задержке». */
  main: string | null;
}

export type ShareCard = ProblemCard | SolutionCard;

type StageLike = Pick<Schemas["PublicStage"], "key" | "type" | "metrics">;

/** The metrics of the cards (delay, area, cells, flops) of the synthesis stage, if there is one. */
export function synthMetrics(stages: readonly StageLike[]): ShareMetric[] {
  const synth = stages.find((stage) => stage.type === "synth");
  if (synth === undefined) return [];
  return CARD_METRICS.flatMap((metric) => {
    const value = synth.metrics[metric];
    return typeof value === "number" ? [{ key: `${synth.key}.${metric}`, value }] : [];
  });
}

export function problemCard(
  problem: Pick<
    Schemas["ProblemDetail"],
    "title" | "tags" | "acceptance" | "leaderboard" | "difficulty"
  >,
  level: ShareLevel | null,
  tags: readonly Schemas["Tag"][],
): ProblemCard {
  return {
    kind: "problem",
    title: problem.title,
    level,
    tags: problem.tags.map((slug) => tags.find((tag) => tag.slug === slug)?.title ?? slug),
    acceptance: problem.acceptance,
    order: problem.leaderboard?.order ?? [],
  };
}

export function solutionCard(
  solution: Schemas["Solution"],
  level: ShareLevel | null,
): SolutionCard {
  const { placement } = solution;
  return {
    kind: "solution",
    title: solution.problem.title,
    level,
    nick: solution.author.nick,
    status: solution.status,
    metrics: synthMetrics(solution.stages),
    placement: placement === null ? null : { rank: placement.rank, total: placement.total },
    main: solution.order[0]?.metric ?? null,
  };
}
