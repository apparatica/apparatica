"""The guest cookie `ap_guest` (FR-GST-01, ADR-0010): a signed random UUID, set with the first
submission and kept for a year. Without a valid cookie a request has no guest: a forged or broken
cookie is ignored, and the next submission starts a new guest.

Format: `<uuid>.<mac>`, the MAC is HMAC-SHA256 over `ap_guest:<uuid>`, base64url without padding.
"""

import base64
import hashlib
import hmac
import uuid
from typing import Annotated

from fastapi import Depends, Request, Response

COOKIE = "ap_guest"
MAX_AGE_S = 365 * 86400


class GuestCookies:
    def __init__(self, key: bytes, *, secure: bool) -> None:
        if len(key) < 32:
            raise ValueError("the guest cookie key must have at least 32 bytes")
        self._key, self._secure = key, secure

    def _mac(self, guest_id: uuid.UUID) -> str:
        digest = hmac.new(self._key, f"{COOKIE}:{guest_id}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def value(self, guest_id: uuid.UUID) -> str:
        return f"{guest_id}.{self._mac(guest_id)}"

    def read(self, request: Request) -> uuid.UUID | None:
        raw = request.cookies.get(COOKIE)
        if raw is None:
            return None
        text, _, mac = raw.partition(".")
        try:
            guest_id = uuid.UUID(text)
        except ValueError:
            return None
        return guest_id if hmac.compare_digest(mac, self._mac(guest_id)) else None

    def set(self, response: Response, guest_id: uuid.UUID) -> None:
        response.set_cookie(
            COOKIE,
            self.value(guest_id),
            max_age=MAX_AGE_S,
            path="/",
            secure=self._secure,
            httponly=True,
            samesite="lax",
        )


def current_guest(request: Request) -> uuid.UUID | None:
    """FastAPI dependency: the guest of the request, if its cookie is valid."""
    cookies: GuestCookies = request.app.state.guest_cookies
    return cookies.read(request)


Guest = Annotated[uuid.UUID | None, Depends(current_guest)]
