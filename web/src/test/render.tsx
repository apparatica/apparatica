import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";

import messages from "../../messages/ru.json";

function Providers({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="ru" messages={messages} timeZone="Europe/Moscow">
      {children}
    </NextIntlClientProvider>
  );
}

/** render() with the providers of the root layout. */
export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, { wrapper: Providers, ...options });
}
