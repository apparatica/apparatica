import { useFormatter, useTranslations } from "next-intl";

/** Formats a duration in seconds with one decimal, as the pipeline writes it: "1,4 с". */
export function useSeconds(): (ms: number) => string {
  const format = useFormatter();
  const t = useTranslations("domain");
  return (ms) =>
    t("seconds", {
      value: format.number(ms / 1000, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    });
}
