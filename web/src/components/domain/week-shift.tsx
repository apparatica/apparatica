import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslations } from "next-intl";

/** The places gained or lost in the global leaderboard for 7 days (FR-LB-05): «↑ +5 за неделю»;
 * nothing when the user was not ranked a week ago. */
export function WeekShift({ delta }: { delta: number | null }) {
  const t = useTranslations("rating.mine");
  if (delta === null) return null;
  if (delta === 0) return <span className="text-mu">{t("weekSame")}</span>;
  const Icon = delta > 0 ? ArrowUp : ArrowDown;
  return (
    <span className="inline-flex items-center gap-1">
      <Icon size={14} aria-hidden="true" className={delta > 0 ? "text-ok" : "text-mu"} />
      {t(delta > 0 ? "weekUp" : "weekDown", { count: Math.abs(delta) })}
    </span>
  );
}
