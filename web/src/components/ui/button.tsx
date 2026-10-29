import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD: 30 px high (44 px on touch screens), radius 3 px, 12.5 px text.
// `outline` is the accent outline of Run on the problem page (mock-up Bench).
export const buttonVariants = cva(
  "inline-flex h-[30px] cursor-pointer items-center justify-center gap-[7px] rounded-md border px-2.5 text-[12.5px] whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-45 aria-disabled:cursor-not-allowed aria-disabled:opacity-45 pointer-coarse:h-11 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // Hover outlines the inside: a translucent fill would cost the text its AA contrast.
        primary:
          "border-ac bg-ac font-medium text-acx enabled:hover:shadow-[inset_0_0_0_1px_var(--acx)]",
        default: "border-bc bg-sf text-tx enabled:hover:bg-sf2",
        outline: "border-ac bg-sf text-ac enabled:hover:bg-acs",
        ghost:
          "border-transparent bg-transparent text-mu enabled:hover:bg-sf2 enabled:hover:text-tx",
        selected: "border-ac bg-acs text-ac",
      },
      size: {
        default: "",
        icon: "w-[30px] px-0 pointer-coarse:w-11",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Renders the child (a link) with the look of a button. */
    asChild?: boolean;
    /** A check in progress: a spinner, and the button does nothing. */
    loading?: boolean;
  };

export function Button({
  className,
  variant,
  size,
  asChild = false,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  if (asChild) {
    return (
      <Slot.Root className={cn(buttonVariants({ variant, size }), className)} {...props}>
        {children}
      </Slot.Root>
    );
  }
  return (
    <button
      type="button"
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <LoaderCircle className="animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}
