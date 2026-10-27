// A tag of a problem and a tag filter (components.md, "Сложность и теги"): plain, selected, and
// selected with a reset (an x). The element is the caller's: a span, or a link or a button
// through `asChild`.
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export type TagChipProps = {
  /** A filter that is on. */
  selected?: boolean;
  /** A filter that is on and resets on click: the x icon. */
  removable?: boolean;
  /** Renders the child (a link, a button) with the look of the chip. */
  asChild?: boolean;
} & ComponentProps<"span">;

export function TagChip({
  selected = false,
  removable = false,
  asChild = false,
  className,
  children,
  ...props
}: TagChipProps) {
  const t = useTranslations("domain.tag");
  const Root = asChild ? Slot.Root : "span";
  const on = selected || removable;
  return (
    <Root
      data-selected={on || undefined}
      className={cn(
        "inline-flex h-5 items-center gap-[5px] rounded-sm border px-[7px] font-mono text-[11px] whitespace-nowrap",
        on ? "border-ac bg-acs text-ac" : "border-bd text-mu",
        className,
      )}
      {...props}
    >
      <Slot.Slottable>{children}</Slot.Slottable>
      {removable && (
        <>
          <X size={12} aria-hidden="true" className="flex-none" />
          <span className="sr-only"> {t("remove")}</span>
        </>
      )}
    </Root>
  );
}
