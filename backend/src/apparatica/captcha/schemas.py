"""The ALTCHA challenge of `GET /captcha/challenge` (specs/05 §3)."""

from typing import Literal

from pydantic import BaseModel, Field


class CaptchaChallenge(BaseModel):
    """An ALTCHA challenge: the widget finds the number and sends the solution as `captcha`."""

    algorithm: Literal["SHA-256"]
    challenge: str = Field(description="Hash to find, hex")
    maxnumber: int = Field(description="Upper bound of the number to find")
    salt: str
    signature: str = Field(description="HMAC of the challenge by the server, hex")
