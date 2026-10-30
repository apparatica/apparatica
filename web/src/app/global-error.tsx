"use client";

import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./globals.css";

import { NextIntlClientProvider } from "next-intl";
import { useEffect } from "react";

import { ServerErrorState } from "@/features/errors/states";
import { LOCALE, TIME_ZONE } from "@/i18n/locale";
import { parseTheme, THEME_COOKIE, THEME_SCRIPT } from "@/lib/theme";

import messages from "../../messages/ru.json";

// The root layout itself failed: the page renders without it, so it brings its own document,
// styles, messages and theme.
export default function GlobalError({ error }: { error: unknown; retry: () => void }) {
  // THEME_SCRIPT follows the system; an explicit choice is the server's part, done here instead.
  useEffect(() => {
    const cookie = new RegExp(`(?:^|; )${THEME_COOKIE}=([^;]*)`).exec(document.cookie);
    const theme = parseTheme(cookie?.[1]);
    if (theme !== "system") document.documentElement.dataset["theme"] = theme;
  }, []);
  const digest =
    typeof error === "object" && error !== null && "digest" in error ? String(error.digest) : null;
  return (
    <html lang={LOCALE} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="bg-sf text-tx">
        <NextIntlClientProvider locale={LOCALE} messages={messages} timeZone={TIME_ZONE}>
          <ServerErrorState digest={digest} onRefresh={() => location.reload()} />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
