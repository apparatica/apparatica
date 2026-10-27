import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// The type scale of globals.css: without it tailwind-merge takes `text-caption` for a colour, and
// `text-caption text-mu` would lose the size.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "display",
            "title-1",
            "title-2",
            "statement",
            "body",
            "caption",
            "label",
            "code",
            "metric",
          ],
        },
      ],
    },
  },
});

/** Joins class names; later Tailwind utilities override conflicting earlier ones (shadcn/ui). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
