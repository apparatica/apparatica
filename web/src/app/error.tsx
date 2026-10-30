"use client";

import { ErrorState } from "@/features/errors/states";

// A failure of a page: the shell stays, the page gives way to the card (specs/08 §1).
export default function PageError({ error, retry }: { error: unknown; retry: () => void }) {
  return <ErrorState error={error} retry={retry} />;
}
