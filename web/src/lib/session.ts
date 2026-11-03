// The session cookie of the API (ADR-0010). It is httpOnly: scripts cannot read it, but the server
// of the site sees it and renders the header of a signed-in user without waiting for GET /me.
export const SESSION_COOKIE = "ap_session";

/** `next` of a login, if it is a path of the site: the rule of the API (docs/api.md, `next`) —
 * a leading "/", but not "//" or "/\", and no whitespace. Anything else is dropped. */
export function sitePath(value: unknown): string | null {
  if (typeof value !== "string" || !value.startsWith("/")) return null;
  if (value.startsWith("//") || value.startsWith("/\\") || /\s/.test(value)) return null;
  return value;
}

/** The login page, returning to `next` afterwards. The login pages themselves are not returned
 * to. */
export function loginHref(next?: string | null): string {
  const back = sitePath(next);
  if (back === null || back === "/" || back.startsWith("/login")) return "/login";
  // Slashes stay readable: "/login?next=/problems/mux4".
  return `/login?next=${encodeURIComponent(back).replaceAll("%2F", "/")}`;
}
