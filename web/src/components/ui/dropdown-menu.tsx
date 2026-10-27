"use client";

import { Check } from "lucide-react";
import { DropdownMenu as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD: items 28 px, the active one --acs / --ac, a shortcut on the right.
export const DropdownMenu = Primitive.Root;
export const DropdownMenuTrigger = Primitive.Trigger;
export const DropdownMenuGroup = Primitive.Group;
export const DropdownMenuRadioGroup = Primitive.RadioGroup;

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-[210px] rounded-md border border-bd bg-sf p-1 text-tx shadow-pop",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}

const item =
  "flex h-7 cursor-pointer items-center gap-2 rounded-sm px-2 text-[12.5px] outline-none! select-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-45 data-[highlighted]:bg-acs data-[highlighted]:text-ac pointer-coarse:h-11 [&_svg]:size-3.5 [&_svg]:flex-none";

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return <Primitive.Item className={cn(item, className)} {...props} />;
}

/** A choice of a radio group: the chosen one has a check on the right. */
export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: ComponentProps<typeof Primitive.RadioItem>) {
  return (
    <Primitive.RadioItem className={cn(item, className)} {...props}>
      {children}
      <Primitive.ItemIndicator className="ml-auto">
        <Check aria-hidden="true" />
      </Primitive.ItemIndicator>
    </Primitive.RadioItem>
  );
}

/** A choice of several: a box on the left, checked when the item is on. */
export function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: ComponentProps<typeof Primitive.CheckboxItem>) {
  return (
    <Primitive.CheckboxItem className={cn(item, "group", className)} {...props}>
      <span
        aria-hidden="true"
        className="inline-flex size-3.5 flex-none items-center justify-center rounded-sm border border-bc bg-ed group-data-[state=checked]:border-ac group-data-[state=checked]:bg-ac group-data-[state=checked]:text-acx"
      >
        <Primitive.ItemIndicator className="inline-flex">
          <Check className="size-3!" strokeWidth={3} />
        </Primitive.ItemIndicator>
      </span>
      {children}
    </Primitive.CheckboxItem>
  );
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof Primitive.Label>) {
  return (
    <Primitive.Label
      className={cn("px-2 py-1.5 font-mono text-label text-mu uppercase", className)}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentProps<typeof Primitive.Separator>) {
  return <Primitive.Separator className={cn("-mx-1 my-1 h-px bg-bd", className)} {...props} />;
}

/** The shortcut of an item, on the right. */
export function DropdownMenuShortcut({ className, ...props }: ComponentProps<"span">) {
  return (
    <span className={cn("ml-auto font-mono text-[10.5px] opacity-80", className)} {...props} />
  );
}
