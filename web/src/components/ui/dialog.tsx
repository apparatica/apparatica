"use client";

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Dialog as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// Floating windows (ModalsA, ModalsB): --sf with a --bd border and shadow-window; the page behind
// is not dimmed.
export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;

export function DialogContent({
  className,
  children,
  closable = true,
  ...props
}: ComponentProps<typeof Primitive.Content> & { closable?: boolean }) {
  const t = useTranslations("ui");
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-0 z-50" />
      <Primitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-32px)] w-[calc(100vw-32px)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-bd bg-sf text-tx shadow-window",
          className,
        )}
        {...props}
      >
        {children}
        {closable && (
          <Primitive.Close
            aria-label={t("close")}
            className="absolute top-4 right-4 flex size-6 cursor-pointer items-center justify-center rounded-md text-mu hover:bg-sf2 hover:text-tx"
          >
            <X size={16} aria-hidden="true" />
          </Primitive.Close>
        )}
      </Primitive.Content>
    </Primitive.Portal>
  );
}

export function DialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-0.5 px-5 pt-5 pr-12", className)} {...props} />;
}

export function DialogTitle({ className, ...props }: ComponentProps<typeof Primitive.Title>) {
  return <Primitive.Title className={cn("text-title-2", className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: ComponentProps<typeof Primitive.Description>) {
  return <Primitive.Description className={cn("text-mu", className)} {...props} />;
}

export function DialogBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("min-h-0 overflow-auto px-5 py-4", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("flex justify-end gap-2 border-t border-bd bg-sf2 px-5 py-3", className)}
      {...props}
    />
  );
}
