// Metrics of the leaderboards as people read them (FR-LB-01): `<stage key>.<metric>` keys get a
// name, a unit and the precision of the tool (ADR-0007: delay to 3 digits, area to 2). A metric
// without a name in the messages is shown by its key.
import { useFormatter, useTranslations } from "next-intl";

import type { MetricComparison } from "@/components/domain/metric-card";
import type { Schemas } from "@/lib/api/client";

/** Metrics of `synth/v1` with a name in words. */
export const METRIC_NAMES = [
  "critical_path_ns",
  "fmax_mhz",
  "area_um2",
  "cells",
  "flops",
  "logic_depth",
] as const;
export type MetricName = (typeof METRIC_NAMES)[number];

export const isMetricName = (name: string): name is MetricName =>
  (METRIC_NAMES as readonly string[]).includes(name);

/** The metrics of the cards of a synthesis, in the order of the mock-ups; all of them are better
 * when lower. */
export const CARD_METRICS = ["critical_path_ns", "area_um2", "cells", "flops"] as const;
export type CardMetric = (typeof CARD_METRICS)[number];

/** The metric of a key: "synth.area_um2" → "area_um2". */
export const metricOf = (key: string): string => key.slice(key.indexOf(".") + 1);

const DIGITS: Record<MetricName, number> = {
  critical_path_ns: 3,
  fmax_mhz: 0,
  area_um2: 2,
  cells: 0,
  flops: 0,
  logic_depth: 0,
};
const UNITS = ["critical_path_ns", "fmax_mhz", "area_um2"] as const;
type UnitName = (typeof UNITS)[number];
const hasUnit = (name: MetricName): name is UnitName => (UNITS as readonly string[]).includes(name);

/** Fraction digits of a metric; unknown ones are shown to 3. */
export const digitsOf = (key: string): number => {
  const name = metricOf(key);
  return isMetricName(name) ? DIGITS[name] : 3;
};

export type Direction = Schemas["LeaderboardKey"]["dir"];

/** The direction of a metric: the formula tells it for its own metrics, the others are better
 * when lower. */
export function directionOf(
  key: string,
  order: readonly Schemas["LeaderboardKey"][] | null | undefined,
): Direction {
  return order?.find((item) => item.metric === key)?.dir ?? "asc";
}

/** The value against the reference: better, worse or the same, and by what share of it. */
export function compareMetric(value: number, reference: number, dir: Direction): MetricComparison {
  if (value === reference) return { kind: "same" };
  const better = dir === "asc" ? value < reference : value > reference;
  return {
    kind: better ? "better" : "worse",
    share: reference === 0 ? null : Math.abs(value - reference) / Math.abs(reference),
  };
}

export interface MetricWords {
  /** "задержка"; the key itself without a name. */
  name: (key: string) => string;
  /** "нс", "µm²"; null for counts. */
  unit: (key: string) => string | null;
  /** The number in the locale, to the precision of the tool: "0,84". */
  value: (key: string, value: number) => string;
  /** The number with its unit: "0,84 нс". */
  withUnit: (key: string, value: number) => string;
  /** The number in a line of text, counts with their noun: "0,84 нс", "162 ячейки". */
  inline: (key: string, value: number) => string;
}

export function useMetricWords(): MetricWords {
  const t = useTranslations("leaderboard");
  const format = useFormatter();
  const name = (key: string) => {
    const metric = metricOf(key);
    return isMetricName(metric) ? t(`metric.${metric}`) : key;
  };
  const unit = (key: string) => {
    const metric = metricOf(key);
    return isMetricName(metric) && hasUnit(metric) ? t(`unit.${metric}`) : null;
  };
  const value = (key: string, number: number) =>
    format.number(number, { maximumFractionDigits: digitsOf(key) });
  const withUnit = (key: string, number: number) => {
    const suffix = unit(key);
    return suffix === null ? value(key, number) : `${value(key, number)} ${suffix}`;
  };
  const inline = (key: string, number: number) => {
    const metric = metricOf(key);
    if (!isMetricName(metric)) return `${key} ${value(key, number)}`;
    if (hasUnit(metric)) return withUnit(key, number);
    return t(`count.${metric}`, { count: number });
  };
  return { name, unit, value, withUnit, inline };
}

/** «Задержка — …. Места: задержка → площадь → время отправки; …». */
export function useOrderWords(order: readonly Schemas["LeaderboardKey"][]) {
  const t = useTranslations("leaderboard");
  const words = useMetricWords();
  const names = [...order.map(({ metric }) => words.name(metric)), t("then")].join(" → ");
  const main = order[0] === undefined ? null : metricOf(order[0].metric);
  return {
    names,
    explain:
      main !== null && isMetricName(main)
        ? `${t(`explain.${main}`)} ${t("explain.order", { order: names })}`
        : t("explain.order", { order: names }),
  };
}
