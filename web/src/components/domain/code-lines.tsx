// Numbered lines of code (CodeViewer): `.code-lines` numbers each `.line` by a counter in its
// `::before`, so the numbers are not selected or copied with the code. Plain here; `SvCode`
// renders the same markup highlighted.
import { cn } from "@/lib/utils";

/** The lines of `code` as Shiki renders them, without colours. */
export function CodeLines({ code, className }: { code: string; className?: string }) {
  const lines = code.replace(/\n$/, "").split("\n");
  return (
    <pre className={cn("code-lines", className)}>
      <code>
        {lines.map((line, index) => (
          <span key={index}>
            <span className="line">{line}</span>
            {index < lines.length - 1 && "\n"}
          </span>
        ))}
      </code>
    </pre>
  );
}
