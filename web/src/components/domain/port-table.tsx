// The ports of a problem (FR-PRB-03, mock-up Bench, "Интерфейс"): name, direction, width and
// purpose, from the `interface` of the package — authors do not repeat it in the statement.
import { useTranslations } from "next-intl";

import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export type Port = Schemas["Port"];

export function PortTable({ ports, className }: { ports: Port[]; className?: string }) {
  const t = useTranslations("statement");
  return (
    <table className={cn("w-full border-collapse text-[12.5px] leading-[18px]", className)}>
      <caption className="mb-1.5 text-left font-mono text-label text-mu uppercase">
        {t("interface")}
      </caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">{t("port.name")}</th>
          <th scope="col">{t("port.dir")}</th>
          <th scope="col">{t("port.width")}</th>
          <th scope="col">{t("port.description")}</th>
        </tr>
      </thead>
      <tbody className="border border-bd">
        {ports.map((port) => (
          <tr key={port.name} className="border-b border-bd last:border-b-0">
            <th
              scope="row"
              className="py-[5px] pr-2 pl-2.5 text-left align-top font-mono text-caption font-medium whitespace-nowrap text-ac"
            >
              {port.name}
            </th>
            <td className="px-2 py-[5px] align-top whitespace-nowrap text-mu">
              {t(`port.${port.dir}`)}
            </td>
            <td className="px-2 py-[5px] align-top font-mono text-caption whitespace-nowrap text-mu">
              {port.signed ? t("port.signed", { width: port.width }) : port.width}
            </td>
            <td className="w-full py-[5px] pr-2.5 pl-2 align-top">{port.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
