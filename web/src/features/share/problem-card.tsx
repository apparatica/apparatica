"use client";

// The card of the open problem, built by the server from the problem, its level and the titles of
// its tags: the banner of an accepted Submit shares the problem (a guest) or takes its title and
// level for the card of the solution.
import { createContext, type ReactNode, useContext } from "react";

import type { ProblemCard } from "./card";

const ProblemCardContext = createContext<ProblemCard | null>(null);

export function ProblemCardProvider({
  card,
  children,
}: {
  card: ProblemCard;
  children: ReactNode;
}) {
  return <ProblemCardContext value={card}>{children}</ProblemCardContext>;
}

/** null outside a problem page. */
export const useProblemCard = (): ProblemCard | null => useContext(ProblemCardContext);
