import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./globals.css";

import type { Metadata } from "next";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/shell/app-shell";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FinishNotices } from "@/features/submission/finish-notices";
import { LOCALE } from "@/i18n/request";
import { ApiMocking } from "@/mocks/api-mocking";
import { QueryProvider } from "@/lib/query";
import { GUEST_BANNER_COOKIE, isGuestBannerClosed } from "@/lib/guest-banner";
import { parseTheme, THEME_COOKIE, THEME_SCRIPT } from "@/lib/theme";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: { default: t("title"), template: `%s · ${t("title")}` },
    description: t("description"),
  };
}

export default async function RootLayout({ children, breadcrumbs, statusbar }: LayoutProps<"/">) {
  const jar = await cookies();
  const theme = parseTheme(jar.get(THEME_COOKIE)?.value);
  // Everyone is a guest until accounts (Ф2).
  const guestBanner = !isGuestBannerClosed(jar.get(GUEST_BANNER_COOKIE)?.value);
  return (
    // An explicit choice is rendered by the server; "system" is set by THEME_SCRIPT before the
    // first paint, so the attribute may differ from the server markup.
    <html
      lang={LOCALE}
      data-theme={theme === "system" ? undefined : theme}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <NextIntlClientProvider>
          <QueryProvider>
            <TooltipProvider>
              <AppShell
                theme={theme}
                guestBanner={guestBanner}
                breadcrumbs={breadcrumbs}
                statusbar={statusbar}
              >
                {process.env.NEXT_PUBLIC_API_MOCKING === "enabled" ? (
                  <ApiMocking>{children}</ApiMocking>
                ) : (
                  children
                )}
              </AppShell>
              <Toaster />
              <FinishNotices />
            </TooltipProvider>
          </QueryProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
