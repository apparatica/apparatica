// next-intl without locale routing: the interface has one locale, ru (AGENTS.md: every string goes
// through messages/ru.json).
import { getRequestConfig } from "next-intl/server";

import messages from "../../messages/ru.json";

import { LOCALE, TIME_ZONE } from "./locale";

export { LOCALE };

export default getRequestConfig(() =>
  Promise.resolve({ locale: LOCALE, messages, timeZone: TIME_ZONE }),
);
