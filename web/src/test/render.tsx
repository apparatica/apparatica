import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { type ReactElement, type ReactNode, useState } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/lib/query";

import messages from "../../messages/ru.json";

/** A query client of one test: no cache shared between tests, no retries of failed requests. */
export function testQueryClient() {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, retry: false } });
  return client;
}

/** The providers of the root layout. */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(testQueryClient);
  return (
    <NextIntlClientProvider locale="ru" messages={messages} timeZone="Europe/Moscow">
      <QueryClientProvider client={client}>
        <TooltipProvider>{children}</TooltipProvider>
      </QueryClientProvider>
    </NextIntlClientProvider>
  );
}

/** render() with the providers of the root layout. */
export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, { wrapper: Providers, ...options });
}
