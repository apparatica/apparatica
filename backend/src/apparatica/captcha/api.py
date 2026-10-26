"""`GET /captcha/challenge` (specs/05 §3, phase 1): the contract, a stub until T1.7."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apparatica.core.errors import ApiError, ErrorCode, problem_responses

router = APIRouter(tags=["captcha"])

PHASE_1 = {"x-phase": 1}


class CaptchaChallenge(BaseModel):
    """An ALTCHA challenge: the widget finds the number and sends the solution as `captcha`."""

    algorithm: Literal["SHA-256"]
    challenge: str = Field(description="Hash to find, hex")
    maxnumber: int = Field(description="Upper bound of the number to find")
    salt: str
    signature: str = Field(description="HMAC of the challenge by the server, hex")


@router.get(
    "/captcha/challenge",
    response_model=CaptchaChallenge,
    responses=problem_responses(ErrorCode.NOT_IMPLEMENTED),
    openapi_extra=PHASE_1,
)
async def get_captcha_challenge() -> CaptchaChallenge:
    """A new challenge for the next submission after CAPTCHA_REQUIRED."""
    raise ApiError(ErrorCode.NOT_IMPLEMENTED, "Declared by the phase 1 contract; arrives in T1.7")
