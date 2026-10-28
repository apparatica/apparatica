"use client";

import { Tabs as Primitive } from "radix-ui";
import { type ComponentProps, createContext, use } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD. `line`: the active tab has a 2 px --ac underline and weight 500.
// `segmented` (a period switch): the chosen segment is --acs with an underline. `panel` (the panels
// of the problem page, mock-up Bench): 36 px tabs on --sf2, the active one --sf with a 2 px --ac
// line on top.
type Variant = "line" | "segmented" | "panel";

const LIST: Record<Variant, string> = {
  line: "flex gap-[18px] border-b border-bd",
  segmented: "inline-flex overflow-hidden rounded-md border border-bc",
  panel: "flex overflow-hidden border-b border-bd bg-sf2",
};

const TRIGGER: Record<Variant, string> = {
  line: "py-1.5 data-[state=active]:font-medium data-[state=active]:text-tx data-[state=active]:shadow-[inset_0_-2px_0_var(--ac)]",
  segmented:
    "h-7 border-l border-bd px-3 first:border-l-0 focus-visible:-outline-offset-2! data-[state=active]:bg-acs data-[state=active]:font-medium data-[state=active]:text-ac data-[state=active]:shadow-[inset_0_-2px_0_var(--ac)] pointer-coarse:h-11",
  panel:
    "h-9 border-r border-bd px-3.5 text-[13px] shadow-[inset_0_2px_0_transparent] focus-visible:-outline-offset-2! data-[state=active]:bg-sf data-[state=active]:text-tx data-[state=active]:shadow-[inset_0_2px_0_var(--ac)] pointer-coarse:h-11",
};

const VariantContext = createContext<Variant>("line");

export const Tabs = Primitive.Root;

export function TabsList({
  variant = "line",
  className,
  ...props
}: ComponentProps<typeof Primitive.List> & { variant?: Variant | undefined }) {
  return (
    <VariantContext value={variant}>
      <Primitive.List className={cn(LIST[variant], className)} {...props} />
    </VariantContext>
  );
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof Primitive.Trigger>) {
  const variant = use(VariantContext);
  return (
    <Primitive.Trigger
      className={cn(
        "inline-flex cursor-pointer items-center gap-1.5 text-[12.5px] whitespace-nowrap text-mu hover:text-tx disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:size-3.5",
        TRIGGER[variant],
        className,
      )}
      {...props}
    />
  );
}

export const TabsContent = Primitive.Content;
