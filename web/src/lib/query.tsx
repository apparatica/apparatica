"use client";

// TanStack Query for the data the browser loads from the API (ADR-0001).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // One client per browser tab; on the server, one per request.
  const [client] = useState(createQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
