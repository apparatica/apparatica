"use client";

// Phones: narrower than 640 px, the `sm` breakpoint of Tailwind (FR-MOB-01). What only looks
// different there is CSS (`max-sm:`, `sm:`); what renders other components — the list of the
// catalogue, the problem page without the editor — asks usePhone(). The server cannot know the
// width, so it guesses from the User-Agent; after hydration the width decides.
import { createContext, type ReactNode, use, useSyncExternalStore } from "react";

export const PHONE_QUERY = "(max-width: 639.98px)";

const PhoneGuess = createContext(false);

/** The guess of the server for the first render: a phone by its User-Agent. */
export function ViewportProvider({ phone, children }: { phone: boolean; children: ReactNode }) {
  return <PhoneGuess value={phone}>{children}</PhoneGuess>;
}

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(PHONE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const matches = () => window.matchMedia(PHONE_QUERY).matches;

/** The window is as narrow as a phone; follows its resizes. */
export function usePhone(): boolean {
  const guess = use(PhoneGuess);
  return useSyncExternalStore(subscribe, matches, () => guess);
}
