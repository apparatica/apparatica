import { CircleX, Search } from "lucide-react";
import { type ComponentProps, type ReactNode, useId } from "react";

import { cn } from "@/lib/utils";

// components.md, sheet CmpD: border --bc on --ed; focus — a 2 px --ac outline; an error — an --er
// border and a message with circle-x under the field; disabled — 50% opacity on --sf2.
const field =
  "h-[30px] rounded-md border border-bc bg-ed px-2.5 text-[12.5px] text-tx placeholder:text-mu pointer-coarse:h-11";
const invalid = "aria-invalid:border-er aria-invalid:shadow-[inset_0_0_0_1px_var(--er)]";
const off = "disabled:cursor-not-allowed disabled:bg-sf2 disabled:opacity-50";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(field, invalid, off, "w-full min-w-0", className)}
      {...props}
    />
  );
}

/** The props a field passes to its control: the label, the hint and the error point to it. */
export interface FieldControl {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

export interface FieldProps {
  label: ReactNode;
  /** A note under the field; the error takes its place. */
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: (control: FieldControl) => ReactNode;
}

/** A label, a control and a note or an error under it. */
export function Field({ label, hint, error, className, children }: FieldProps) {
  const id = useId();
  const note = error ?? hint;
  const noteId = `${id}-note`;
  return (
    <div className={cn("flex min-w-0 flex-col gap-[5px]", className)}>
      <label htmlFor={id} className="text-caption font-medium">
        {label}
      </label>
      {children({
        id,
        ...(note != null && { "aria-describedby": noteId }),
        ...(error != null && { "aria-invalid": true }),
      })}
      {note != null && (
        <p
          id={noteId}
          className={cn(
            "flex items-center gap-[5px] text-[11.5px]",
            error != null ? "text-er" : "text-mu",
          )}
        >
          {error != null && <CircleX size={14} aria-hidden="true" className="flex-none" />}
          {note}
        </p>
      )}
    </div>
  );
}

/** A search field: the icon, the input and a hint of its key on the right ("/"). */
export function SearchInput({
  className,
  hint,
  ...props
}: Omit<ComponentProps<"input">, "type"> & { hint?: ReactNode }) {
  return (
    <div
      className={cn(
        field,
        "flex items-center gap-2 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-ac has-[input:disabled]:bg-sf2 has-[input:disabled]:opacity-50",
        className,
      )}
    >
      <Search size={14} aria-hidden="true" className="flex-none text-mu" />
      <input
        type="search"
        className="h-full min-w-0 flex-1 bg-transparent outline-none! placeholder:text-mu disabled:cursor-not-allowed [&::-webkit-search-cancel-button]:hidden"
        {...props}
      />
      {hint != null && <span className="flex-none text-mu">{hint}</span>}
    </div>
  );
}
