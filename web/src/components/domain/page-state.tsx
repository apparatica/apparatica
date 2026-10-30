import type { LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageStateProps extends Omit<ComponentProps<"section">, "title"> {
  icon: LucideIcon;
  title: ReactNode;
  /** What happened and what to do. */
  description: ReactNode;
  /** The mono line under the text: "404 · /problems/fifo-synk", "500 · ID 7f3a-91c2". */
  code?: ReactNode;
  /** Buttons; the first one is the main action. */
  actions?: ReactNode;
  /** The heading level of the title: h1 for a page of its own. */
  heading?: "h1" | "h2";
}

/** An error or an empty result in place of a page or a list (sheet PageErrors): an icon, a title,
 * the explanation, a code line and the actions, centred. */
export function PageState({
  icon: Icon,
  title,
  description,
  code,
  actions,
  heading: Heading = "h2",
  className,
  ...props
}: PageStateProps) {
  return (
    <section
      className={cn(
        "flex min-h-[300px] flex-col items-center justify-center gap-2.5 px-8 py-9 text-center",
        className,
      )}
      {...props}
    >
      <Icon size={32} aria-hidden="true" className="text-mu" />
      <Heading className="text-[16px] leading-[1.5] font-semibold">{title}</Heading>
      <p className="max-w-[340px] text-mu">{description}</p>
      {code != null && <p className="font-mono text-[11.5px] text-mu">{code}</p>}
      {actions != null && (
        <div className="mt-1.5 flex flex-wrap justify-center gap-2">{actions}</div>
      )}
    </section>
  );
}
