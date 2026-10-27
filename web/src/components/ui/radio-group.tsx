"use client";

import { RadioGroup as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function RadioGroup({ className, ...props }: ComponentProps<typeof Primitive.Root>) {
  return <Primitive.Root className={cn("grid gap-2", className)} {...props} />;
}

// components.md, sheet CmpD: a 16 px circle, border --bc on --ed; chosen — --ac with a 6 px dot.
export function RadioGroupItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return (
    <Primitive.Item
      className={cn(
        "inline-flex size-4 flex-none cursor-pointer items-center justify-center rounded-full border border-bc bg-ed data-[state=checked]:border-ac data-[state=checked]:bg-ac disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <Primitive.Indicator className="size-1.5 rounded-full bg-acx" />
    </Primitive.Item>
  );
}
