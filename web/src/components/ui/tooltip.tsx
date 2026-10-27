"use client";

import { Tooltip as Primitive } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

// components.md: --tx background, --sf text, shadow-pop, at most 210 px, after 300 ms.
export function TooltipProvider({
  delayDuration = 300,
  ...props
}: ComponentProps<typeof Primitive.Provider>) {
  return <Primitive.Provider delayDuration={delayDuration} {...props} />;
}

export const TooltipRoot = Primitive.Root;
export const TooltipTrigger = Primitive.Trigger;

export function TooltipContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-[210px] rounded-md bg-tx px-2.5 py-[7px] text-caption leading-[1.4] text-sf shadow-pop",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}

/** A short hint of the child: plain text, no formatting. */
export function Tooltip({
  content,
  children,
  side,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: ComponentProps<typeof Primitive.Content>["side"];
}) {
  return (
    <TooltipRoot>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent {...(side !== undefined && { side })}>{content}</TooltipContent>
    </TooltipRoot>
  );
}
