import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "../src/app/globals.css";

import type { Decorator, Preview } from "@storybook/nextjs-vite";
import { NextIntlClientProvider } from "next-intl";
import { type ReactNode, useEffect } from "react";

import messages from "../messages/ru.json";

// The theme of the toolbar goes on <html data-theme>, as the root layout renders it.
function Themed({ theme, children }: { theme: "light" | "dark"; children: ReactNode }) {
  useEffect(() => {
    document.documentElement.dataset["theme"] = theme;
  }, [theme]);
  return children;
}

const withTheme: Decorator = (Story, { globals }) => (
  <Themed theme={globals["theme"] === "dark" ? "dark" : "light"}>
    <Story />
  </Themed>
);

const withIntl: Decorator = (Story) => (
  <NextIntlClientProvider locale="ru" messages={messages} timeZone="Europe/Moscow">
    <Story />
  </NextIntlClientProvider>
);

const preview: Preview = {
  decorators: [withTheme, withIntl],
  globalTypes: {
    theme: {
      description: "Тема",
      toolbar: {
        title: "Тема",
        icon: "mirror",
        items: [
          { value: "light", title: "Светлая" },
          { value: "dark", title: "Тёмная" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  parameters: {
    layout: "padded",
    backgrounds: { disable: true },
  },
};

export default preview;
