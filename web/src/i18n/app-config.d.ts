// Typed messages: t("shell.nav.problems") is checked against messages/ru.json.
import type messages from "../../messages/ru.json";

declare module "next-intl" {
  interface AppConfig {
    Locale: "ru";
    Messages: typeof messages;
  }
}
