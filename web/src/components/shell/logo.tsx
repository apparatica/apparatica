import { cn } from "@/lib/utils";

/** The sign of Apparatica: a window with a prompt, in the accent colour. */
export function Logo({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("flex-none stroke-ac", className)}
    >
      <rect x="4" y="3" width="17" height="18" rx="2" />
      <path d="M4 9.5l5 2.5-5 2.5" />
    </svg>
  );
}
