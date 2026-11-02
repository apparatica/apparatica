"""CSRF protection of mutating requests (NFR-SEC-05, ADR-0010): a pure ASGI middleware, so every
route is covered, the routes of later phases included, and streaming responses pass through.

A mutating request (not GET, HEAD, OPTIONS) passes when
- its `Origin` is the origin of the site, which serves the API on its own origin (specs/03 §2); a
  request without `Origin` is judged by the origin of its `Referer`, one without both is not from a
  browser page and is judged by the token alone;
- its header `X-CSRF-Token` equals the cookie `ap_csrf` (double submit): a page of another site
  can neither read the cookie nor set the header without a CORS preflight, which the API refuses.

Otherwise the answer is CSRF_FAILED. The cookie is readable by scripts and holds a random token; a
response to a request without a valid one sets a new one, the CSRF_FAILED answer included: the
frontend repeats a refused request once with it. The token belongs to the browser, not to the
session: login and logout keep it.
"""

import hmac
import re
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apparatica.core.errors import ErrorCode, problem_response

COOKIE = "ap_csrf"
HEADER = "X-CSRF-Token"
MAX_AGE_S = 365 * 86400
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")  # secrets.token_urlsafe(32)


def new_token() -> str:
    return secrets.token_urlsafe(32)


class CsrfMiddleware:
    def __init__(self, app: ASGIApp, *, secure: bool) -> None:
        self.app = app
        self._secure = secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        token = request.cookies.get(COOKIE)
        issued = None if token is not None and _TOKEN.match(token) else new_token()
        if scope["method"] not in SAFE_METHODS:
            failure = _failure(request, None if issued else token)
            if failure is not None:
                response = problem_response(request, ErrorCode.CSRF_FAILED, detail=failure)
                if issued is not None:
                    response.headers.append("set-cookie", self._cookie(issued))
                await response(scope, receive, send)
                return
        if issued is None:
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("set-cookie", self._cookie(issued))
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    def _cookie(self, token: str) -> str:
        """The Set-Cookie value; without HttpOnly: the frontend copies the token into the header."""
        cookie: SimpleCookie = SimpleCookie()
        cookie[COOKIE] = token
        attributes = cookie[COOKIE]
        attributes["max-age"] = MAX_AGE_S
        attributes["path"] = "/"
        attributes["samesite"] = "lax"
        if self._secure:
            attributes["secure"] = True
        return cookie.output(header="").strip()


def _failure(request: Request, token: str | None) -> str | None:
    """Why a mutating request is refused; None: it passes."""
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")) is not None:
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    if origin is not None and origin.lower() != _own_origin(request):
        return "Cross-origin request"
    header = request.headers.get(HEADER)
    if token is None or header is None or not hmac.compare_digest(header.encode(), token.encode()):
        return f"The {HEADER} header must equal the {COOKIE} cookie"
    return None


def _own_origin(request: Request) -> str:
    """The origin of the site as the browser reached it: the scheme comes from the proxy
    (`--forwarded-allow-ips`), the host is kept by it."""
    return f"{request.url.scheme}://{request.url.netloc}".lower()
