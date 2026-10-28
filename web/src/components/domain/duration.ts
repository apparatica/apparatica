import { useFormatter, useTranslations } from "next-intl";

/** Formats a size in kilobytes, whole megabytes as such: "16 кБ", "1 МБ". */
export function useKilobytes(): (kb: number) => string {
  const format = useFormatter();
  return (kb) =>
    kb % 1024 === 0
      ? format.number(kb / 1024, { style: "unit", unit: "megabyte" })
      : format.number(kb, { style: "unit", unit: "kilobyte" });
}

/** Formats a duration in seconds with one decimal, as the pipeline writes it: "1,4 с". */
export function useSeconds(): (ms: number) => string {
  const format = useFormatter();
  const t = useTranslations("domain");
  return (ms) =>
    t("seconds", {
      value: format.number(ms / 1000, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    });
}
