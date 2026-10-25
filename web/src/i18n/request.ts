// next-intl without locale routing: the interface has one locale, ru (AGENTS.md: every string goes
// through messages/ru.json).
import { getRequestConfig } from "next-intl/server";

import messages from "../../messages/ru.json";

export const LOCALE = "ru";

export default getRequestConfig(() =>
  Promise.resolve({ locale: LOCALE, messages, timeZone: "Europe/Moscow" }),
);
