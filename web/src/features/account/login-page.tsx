// The login page (FR-AUTH-01, mock-up Login): what the platform is on the left, the card with the
// logins on the right. The example of a check shows only the stages there are now: synthesis,
// formal properties and the rating join it with their phases (specs/08 §4).
import { CircleCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Schemas } from "@/lib/api/client";

import { LoginCard } from "./login-card";

export interface LoginPageProps {
  providers: Schemas["AuthProvider"][];
  /** Where to return after the login: a path of the site. */
  next: string | null;
  /** Why the last login through a provider failed: `error` of the address. */
  error: string | null;
}

export function LoginPage(props: LoginPageProps) {
  return (
    <div className="flex min-h-full items-center justify-center gap-16 bg-bg px-4 py-6 sm:px-8 sm:py-12 xl:gap-24">
      <Hero />
      <LoginCard {...props} />
    </div>
  );
}

function Hero() {
  const t = useTranslations("login.hero");
  const stages = [
    { name: t("lint"), time: "0,4" },
    { name: t("sim"), time: "3,1" },
  ];
  const metrics = [
    { label: t("openTests"), value: "8", unit: t("of", { total: 8 }) },
    { label: t("hiddenTests"), value: "24", unit: t("of", { total: 24 }) },
    { label: t("duration"), value: "3,5", unit: t("seconds") },
  ];
  return (
    <section
      aria-label={t("label")}
      className="flex max-w-[560px] flex-[0_1_560px] flex-col gap-[22px] max-lg:hidden"
    >
      <div className="flex flex-col gap-2.5">
        <span className="font-mono text-label text-mu uppercase">{t("brand")}</span>
        <h2 className="text-display">{t("title")}</h2>
        <p className="text-[15px] leading-6 text-mu">{t("description")}</p>
      </div>
      <figure
        aria-label={t("example")}
        className="flex flex-col gap-3 rounded-md border border-bd bg-sf px-4 py-3.5"
      >
        <figcaption className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 font-semibold text-ok">
            <CircleCheck size={16} aria-hidden="true" />
            {t("accepted")}
          </span>
          <span className="text-[12.5px] text-mu">{t("problem")}</span>
        </figcaption>
        <ul className="flex gap-1.5">
          {stages.map((stage) => (
            <li
              key={stage.name}
              className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-sm bg-oks px-2.5 py-2 text-ok"
            >
              <span className="flex items-center gap-1.5 text-[12.5px] font-medium">
                <CircleCheck size={13} aria-hidden="true" />
                {stage.name}
              </span>
              <span className="font-mono text-[11px] opacity-90">
                {stage.time} {t("seconds")}
              </span>
            </li>
          ))}
        </ul>
        <dl className="grid grid-cols-3 gap-3">
          {metrics.map((metric) => (
            <div key={metric.label} className="flex flex-col leading-[1.3]">
              <dt className="text-[11.5px] text-mu">{metric.label}</dt>
              <dd className="font-mono text-[16px] font-medium">
                {metric.value}{" "}
                <span className="text-[11px] font-normal text-mu">{metric.unit}</span>
              </dd>
            </div>
          ))}
        </dl>
      </figure>
      <p className="text-[12.5px] text-mu">{t("footer")}</p>
    </section>
  );
}
