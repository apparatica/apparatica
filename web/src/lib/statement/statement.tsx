// The statement of a problem as React elements (FR-PRB-03). Rendered on the server: the page
// sends the HTML of the formulas, diagrams and highlighted code, not the renderers.
import "katex/dist/katex.min.css";
import "./statement.css";

import { toJsxRuntime } from "hast-util-to-jsx-runtime";
import { useTranslations } from "next-intl";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";

import { cn } from "@/lib/utils";

import { renderStatement } from "./render";

export interface StatementProps {
  markdown: string;
  /** The URL of a picture of the package, `assets/…`; without it pictures are left out. */
  assetUrl?: ((path: string) => string) | undefined;
  className?: string;
}

export function Statement({ markdown, assetUrl, className }: StatementProps) {
  const t = useTranslations("statement");
  const { tree } = renderStatement(markdown, { assetUrl, waveformLabel: t("waveform") });
  return (
    <div className={cn("statement", className)}>{toJsxRuntime(tree, { Fragment, jsx, jsxs })}</div>
  );
}
