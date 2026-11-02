// CSRF protection of the API (docs/api.md#пользователи-и-вход-ф2-контракт, ADR-0010): a mutating
// request carries the header X-CSRF-Token with the value of the cookie ap_csrf. The API sets the
// cookie on any response to a request without it, a CSRF_FAILED refusal included: a refused
// request is sent once more with the new token.

export const CSRF_COOKIE = "ap_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

type Send = (request: Request) => Promise<Response>;

/** The value of a cookie of the page; null without it. */
export function readCookie(
  name: string,
  cookies = globalThis.document?.cookie ?? "",
): string | null {
  for (const pair of cookies.split(";")) {
    const [key, ...value] = pair.trim().split("=");
    if (key === name) return decodeURIComponent(value.join("="));
  }
  return null;
}

/** `send` with the token on mutating requests and one repeat after CSRF_FAILED with a new token. */
export function withCsrf(send: Send, token = () => readCookie(CSRF_COOKIE)): Send {
  return async (request) => {
    if (SAFE_METHODS.has(request.method)) return send(request);
    const repeat = request.clone();
    const sent = token();
    const response = await send(signed(request, sent));
    if (response.status !== 403 || !(await refusedByCsrf(response))) return response;
    const fresh = token();
    // Without a new token a repeat is refused again: another origin, a blocked cookie.
    return fresh === sent ? response : send(signed(repeat, fresh));
  };
}

function signed(request: Request, token: string | null): Request {
  if (token !== null) request.headers.set(CSRF_HEADER, token);
  return request;
}

async function refusedByCsrf(response: Response): Promise<boolean> {
  try {
    const body: unknown = await response.clone().json();
    return (body as { code?: unknown } | null)?.code === "CSRF_FAILED";
  } catch {
    return false;
  }
}
