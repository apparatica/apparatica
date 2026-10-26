"""ALTCHA proof-of-work challenges (ADR-0010, decision ОВ-16), the protocol of the widget:

- challenge: `sha256(salt + str(number))` in hex for a random `number <= maxnumber`; the salt ends
  with `?expires=<unix time>`, so the widget and the server both know when it expires;
- signature: HMAC-SHA256 of the challenge with the key of the server, in hex: the server keeps no
  state between the challenge and its solution;
- solution (the `captcha` field): base64 of the JSON `{algorithm, challenge, number, salt,
  signature}` the widget sends back.

A solution is valid once: the caller remembers its signature until the challenge expires.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from typing import Final
from urllib.parse import parse_qs

from apparatica.captcha.schemas import CaptchaChallenge

ALGORITHM: Final = "SHA-256"


class Altcha:
    def __init__(
        self,
        key: bytes,
        *,
        max_number: int,
        expires_s: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(key) < 32:
            raise ValueError("the captcha key must have at least 32 bytes")
        self._key, self._max_number, self._expires_s = key, max_number, expires_s
        self._clock = clock

    def _sign(self, challenge: str) -> str:
        return hmac.new(self._key, challenge.encode(), hashlib.sha256).hexdigest()

    def challenge(self) -> CaptchaChallenge:
        expires = int(self._clock()) + self._expires_s
        salt = f"{secrets.token_hex(12)}?expires={expires}"
        number = secrets.randbelow(self._max_number + 1)
        challenge = hashlib.sha256(f"{salt}{number}".encode()).hexdigest()
        return CaptchaChallenge(
            algorithm=ALGORITHM,
            challenge=challenge,
            maxnumber=self._max_number,
            salt=salt,
            signature=self._sign(challenge),
        )

    def verify(self, payload: str) -> str | None:
        """The signature of a solved, unexpired challenge of this server; None otherwise."""
        try:
            data = json.loads(base64.b64decode(payload, validate=True))
        except (binascii.Error, ValueError):  # not base64, not UTF-8 or not JSON
            return None
        if not isinstance(data, dict):
            return None
        algorithm, challenge = data.get("algorithm"), data.get("challenge")
        number, salt, signature = data.get("number"), data.get("salt"), data.get("signature")
        if (
            algorithm != ALGORITHM
            or not isinstance(challenge, str)
            or not isinstance(salt, str)
            or not isinstance(signature, str)
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 0 <= number <= self._max_number
        ):
            return None
        if not hmac.compare_digest(signature, self._sign(challenge)):
            return None
        solved = hashlib.sha256(f"{salt}{number}".encode()).hexdigest()
        if not hmac.compare_digest(challenge, solved):
            return None
        expires = parse_qs(salt.partition("?")[2]).get("expires", [""])[0]
        if not expires.isdigit() or int(expires) <= self._clock():
            return None
        return signature
