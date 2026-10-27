"use client";

import { Avatar as Primitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Initials of a name: the first letters of up to two words ("Иван Сладков" → "ИС"). */
export function initialsOf(name: string, letters: 1 | 2 = 2): string {
  const words = name.split(/[\s._-]+/).filter(Boolean);
  return words
    .slice(0, letters)
    .map((word) => [...word][0] ?? "")
    .join("")
    .toUpperCase();
}

// Sheet CmpD: 20, 28 and 40 px, a --bc border, initials (one letter in the small ones).
const SIZES = {
  20: { box: "size-5 text-[8px]", letters: 1 },
  28: { box: "size-7 text-[11px]", letters: 1 },
  40: { box: "size-10 text-[16px]", letters: 2 },
} as const;

export function Avatar({
  name,
  src,
  size = 28,
  className,
}: {
  name: string;
  src?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const { box, letters } = SIZES[size];
  return (
    <Primitive.Root
      className={cn(
        "inline-flex flex-none items-center justify-center overflow-hidden rounded-full border border-bc bg-sf2 font-semibold text-tx",
        box,
        className,
      )}
    >
      {src != null && <Primitive.Image src={src} alt={name} className="size-full object-cover" />}
      <Primitive.Fallback aria-label={name} role="img">
        {initialsOf(name, letters)}
      </Primitive.Fallback>
    </Primitive.Root>
  );
}
