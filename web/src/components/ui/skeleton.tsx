import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** A placeholder of loading content: --sf2 with a shimmer (--shim); still with reduced motion. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative overflow-hidden rounded-md bg-sf2 after:absolute after:inset-0 after:[transform:translateX(-100%)] after:animate-shim after:bg-linear-to-r after:from-transparent after:via-[var(--shim)] after:to-transparent after:content-['']",
        className,
      )}
      {...props}
    />
  );
}
