// Dates of the leaderboards as in the mock-up SolutionLB: «сегодня», «вчера», «3 окт.», and
// with the year for another one.
import { useFormatter, useNow, useTranslations } from "next-intl";

const DAY_MS = 86_400_000;

export function useShortDate(): (iso: string) => string {
  const t = useTranslations("leaderboard");
  const format = useFormatter();
  const now = useNow();
  const day = (at: Date) =>
    format.dateTime(at, { year: "numeric", month: "numeric", day: "numeric" });
  const year = (at: Date) => format.dateTime(at, { year: "numeric" });
  return (iso) => {
    const at = new Date(iso);
    if (day(at) === day(now)) return t("today");
    if (day(at) === day(new Date(now.getTime() - DAY_MS))) return t("yesterday");
    return year(at) === year(now)
      ? format.dateTime(at, { day: "numeric", month: "short" })
      : format.dateTime(at, { day: "numeric", month: "short", year: "numeric" });
  };
}
