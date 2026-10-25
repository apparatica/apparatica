"""Job tokens (specs/07 §5.3, ADR-0009): the API signs `{submission_id, attempt_max, exp}` and puts
the token into the queue message; the worker attaches it to every result record, and the
ingestor accepts a result only with a valid token of that submission. The key is known to the API
and the ingestor only, so a compromised worker can spoil only the checks it was given.

Format: `v1.<payload>.<mac>`, base64url without padding; the payload is compact JSON and the MAC
is HMAC-SHA256 over `v1.<payload>`.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

VERSION = "v1"
# Starts of a check before it ends with internal_error (ADR-0002: the counter attempts:<id>).
ATTEMPT_MAX = 2


class InvalidJobTokenError(ValueError):
    pass


@dataclass(frozen=True)
class JobClaims:
    submission_id: uuid.UUID
    attempt_max: int
    exp: int  # Unix time, seconds


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class JobTokens:
    def __init__(self, key: bytes, *, ttl_s: int, clock: Callable[[], float] = time.time) -> None:
        if len(key) < 32:
            raise ValueError("the job token key must have at least 32 bytes")
        self._key, self._ttl_s, self._clock = key, ttl_s, clock

    def _mac(self, signed: str) -> str:
        return _b64(hmac.new(self._key, signed.encode(), hashlib.sha256).digest())

    def issue(self, submission_id: uuid.UUID, attempt_max: int = ATTEMPT_MAX) -> str:
        claims = {
            "submission_id": str(submission_id),
            "attempt_max": attempt_max,
            "exp": int(self._clock()) + self._ttl_s,
        }
        payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
        signed = f"{VERSION}.{payload}"
        return f"{signed}.{self._mac(signed)}"

    def verify(self, token: str, submission_id: uuid.UUID) -> JobClaims:
        """The claims of a token signed by this key for this submission and not expired."""
        try:
            version, payload, mac = token.split(".")
        except ValueError:
            raise InvalidJobTokenError("malformed token") from None
        if version != VERSION:
            raise InvalidJobTokenError(f"unknown token version {version!r}")
        if not hmac.compare_digest(mac, self._mac(f"{version}.{payload}")):
            raise InvalidJobTokenError("bad signature")
        data = json.loads(_unb64(payload))
        claims = JobClaims(uuid.UUID(data["submission_id"]), data["attempt_max"], data["exp"])
        if claims.submission_id != submission_id:
            raise InvalidJobTokenError("the token is for another submission")
        if claims.exp <= self._clock():
            raise InvalidJobTokenError("the token has expired")
        return claims
