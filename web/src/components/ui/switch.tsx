"use client";

import { Switch as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD: 30 × 16 px; off — --bc with an --ed knob, on — --ac with an --acx knob.
export function Switch({ className, ...props }: ComponentProps<typeof Primitive.Root>) {
  return (
    <Primitive.Root
      className={cn(
        "inline-flex h-4 w-[30px] flex-none cursor-pointer items-center rounded-full bg-bc p-0.5 data-[state=checked]:bg-ac disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <Primitive.Thumb className="block size-3 rounded-full bg-ed transition-transform data-[state=checked]:translate-x-3.5 data-[state=checked]:bg-acx" />
    </Primitive.Root>
  );
}
