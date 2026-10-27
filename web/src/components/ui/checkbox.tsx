"use client";

import { Check } from "lucide-react";
import { Checkbox as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD: 16 px, border --bc on --ed; checked — --ac with the mark in --acx.
export function Checkbox({ className, ...props }: ComponentProps<typeof Primitive.Root>) {
  return (
    <Primitive.Root
      className={cn(
        "inline-flex size-4 flex-none cursor-pointer items-center justify-center rounded-md border border-bc bg-ed text-acx data-[state=checked]:border-ac data-[state=checked]:bg-ac disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <Primitive.Indicator>
        <Check size={12} strokeWidth={3} aria-hidden="true" />
      </Primitive.Indicator>
    </Primitive.Root>
  );
}
