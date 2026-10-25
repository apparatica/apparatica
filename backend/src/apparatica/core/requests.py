"""Request id and access log: a pure ASGI middleware, so streaming responses (SSE) pass through.

The id comes from a trusted `X-Request-ID` (the proxy sets it) or is a new UUIDv7. It is bound to
the log context, stored in `request.state.request_id` (problem+json uses it) and returned in the
`X-Request-ID` response header.
"""

import re
import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apparatica.core.ids import uuid7

HEADER = b"x-request-id"
_VALID = re.compile(rb"^[A-Za-z0-9._-]{8,64}$")

log = structlog.get_logger("apparatica.request")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(HEADER, b"")
        request_id = incoming.decode() if _VALID.match(incoming) else str(uuid7())
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500  # until the response starts: an exception escaped the app

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER]
                message["headers"] = [*headers, (HEADER, request_id.encode())]
            await send(message)

        started = time.perf_counter()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log.info(
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")
