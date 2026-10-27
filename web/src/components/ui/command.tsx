"use client";

import { Command as Primitive } from "cmdk";
import { Search } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

import { Kbd } from "./kbd";

// The command palette of sheet CmpD: a 38 px search row, groups with label captions, items 30 px,
// the selected one --acs / --ac, shortcuts or badges on the right.
export function Command({ className, ...props }: ComponentProps<typeof Primitive>) {
  return <Primitive className={cn("flex min-h-0 flex-col text-tx", className)} {...props} />;
}

export function CommandInput({
  className,
  hint,
  ...props
}: ComponentProps<typeof Primitive.Input> & { hint?: ReactNode }) {
  return (
    <div className="flex h-[38px] flex-none items-center gap-2 border-b border-bd px-3">
      <Search size={14} aria-hidden="true" className="flex-none text-mu" />
      <Primitive.Input
        className={cn(
          "h-full min-w-0 flex-1 bg-transparent caret-ac outline-none! placeholder:text-mu",
          className,
        )}
        {...props}
      />
      {hint != null && <Kbd className="text-mu">{hint}</Kbd>}
    </div>
  );
}

export function CommandList({ className, ...props }: ComponentProps<typeof Primitive.List>) {
  return (
    <Primitive.List
      className={cn("max-h-[min(360px,60dvh)] overflow-y-auto p-1", className)}
      {...props}
    />
  );
}

export function CommandEmpty({ className, ...props }: ComponentProps<typeof Primitive.Empty>) {
  return <Primitive.Empty className={cn("px-2 py-6 text-center text-mu", className)} {...props} />;
}

export function CommandLoading({ className, ...props }: ComponentProps<typeof Primitive.Loading>) {
  return (
    <Primitive.Loading className={cn("px-2 py-1.5 text-caption text-mu", className)} {...props} />
  );
}

export function CommandGroup({ className, ...props }: ComponentProps<typeof Primitive.Group>) {
  return (
    <Primitive.Group
      className={cn(
        "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:text-mu [&_[cmdk-group-heading]]:uppercase",
        className,
      )}
      {...props}
    />
  );
}

export function CommandItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return (
    <Primitive.Item
      className={cn(
        "flex h-[30px] cursor-pointer items-center gap-2 rounded-sm px-2 text-[12.5px] select-none data-[disabled=true]:cursor-not-allowed data-[disabled=true]:opacity-45 data-[selected=true]:bg-acs data-[selected=true]:text-ac pointer-coarse:h-11 [&_svg]:size-3.5 [&_svg]:flex-none",
        className,
      )}
      {...props}
    />
  );
}

/** The shortcut or a note of an item, on the right. */
export function CommandShortcut({ className, ...props }: ComponentProps<"span">) {
  return <span className={cn("ml-auto font-mono text-[10.5px] text-mu", className)} {...props} />;
}
