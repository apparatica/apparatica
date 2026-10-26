"""`GET /captcha/challenge` (specs/05 §3, phase 1)."""

from fastapi import APIRouter, Request, Response

from apparatica.captcha.schemas import CaptchaChallenge
from apparatica.core.http import PRIVATE

router = APIRouter(tags=["captcha"])

PHASE_1 = {"x-phase": 1}


@router.get("/captcha/challenge", response_model=CaptchaChallenge, openapi_extra=PHASE_1)
async def get_captcha_challenge(request: Request, response: Response) -> CaptchaChallenge:
    """A new challenge for the next submission after CAPTCHA_REQUIRED; valid once, for the time
    in `?expires=` of its salt."""
    response.headers["Cache-Control"] = PRIVATE
    challenge: CaptchaChallenge = request.app.state.captcha.altcha.challenge()
    return challenge
