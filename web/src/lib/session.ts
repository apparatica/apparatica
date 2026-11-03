// The session cookie of the API (ADR-0010). It is httpOnly: scripts cannot read it, but the server
// of the site sees it and renders the header of a signed-in user without waiting for GET /me.
export const SESSION_COOKIE = "ap_session";
