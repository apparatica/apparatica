"""Platform data from `config/*.yaml`: difficulty levels, the catalogue, limits, the legal
documents and the formula of the global leaderboard, which the frontend shows, and the rate
limits against abuse, which it does not.

Loaded once at startup and validated strictly: a broken file stops the process instead of serving
a half-configured site.
"""

from datetime import date
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, ValidationError

DIFFICULTIES_FILE = "difficulties.yaml"
CATALOG_FILE = "catalog.yaml"
LIMITS_FILE = "limits.yaml"
RATE_LIMITS_FILE = "rate-limits.yaml"
LEGAL_FILE = "legal.yaml"
RATING_FILE = "rating.yaml"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Difficulty(_Model):
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    title: str
    token: Annotated[
        str, Field(description="Colour pair of the design tokens, e.g. e for --e/--es")
    ]


class Catalog(_Model):
    per_page: Annotated[int, Field(ge=1, le=100)]


class SolutionLimits(_Model):
    max_bytes: PositiveInt
    max_lines: PositiveInt


class Quota(_Model):
    checks_per_hour: NonNegativeInt
    concurrent: NonNegativeInt
    heavy_per_day: NonNegativeInt
    waveforms_per_hour: NonNegativeInt


class Quotas(_Model):
    guest: Quota
    user: Quota


class WaveformLimits(_Model):
    view_max_mb: Annotated[
        int,
        Field(ge=1, description="A larger FST is offered for download only, not shown (FR-WAV-02)"),
    ]


class Limits(_Model):
    solution: SolutionLimits
    quotas: Quotas
    waveforms: WaveformLimits


class Window(_Model):
    """At most `limit` events in any `window_s` seconds (a moving window)."""

    limit: PositiveInt
    window_s: PositiveInt


class CaptchaRules(_Model):
    """When a guest check needs a solved ALTCHA challenge (FR-GST-05), and its work."""

    per_guest: Window
    per_ip: Window
    max_number: Annotated[int, Field(ge=1000, le=10_000_000)]
    expires_s: PositiveInt


class RateLimits(_Model):
    requests_per_ip: Window
    requests_per_author: Window
    drafts_per_user: Window
    checks_per_ip: Window
    logins_per_ip: Window
    logins_per_email: Window
    captcha: CaptchaRules


class Operator(_Model):
    """Who processes the personal data of the users (GDPR art. 13), as the documents name them: a
    private person, so a name and a mailbox, no postal address."""

    name: str
    email: str = Field(description="For requests about personal data")


class LegalDocument(_Model):
    version: date = Field(description="The date of the edition; a consent records it")
    sha256: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{64}$",
            description="Of web/content/legal/<key>.md: a test fails on a text changed without a"
            " decision on its version",
        ),
    ]


class LegalDocuments(_Model):
    """What a user accepts at the first login (FR-AUTH-06)."""

    terms: LegalDocument
    privacy: LegalDocument

    def versions(self) -> dict[str, date]:
        return {key: document.version for key, document in self}


class Legal(_Model):
    draft: bool = Field(description="The texts are drafts; the site marks them so")
    operator: Operator
    documents: LegalDocuments


class RatingFormula(_Model):
    """Points of the global leaderboard (FR-LB-05, ADR-0006): for every solved published problem
    by its level, plus a bonus for places 1, 2, 3, ... of the leaderboard of a problem."""

    formula_version: PositiveInt
    solved: dict[str, NonNegativeInt] = Field(description="By the keys of the difficulty levels")
    places: list[NonNegativeInt] = Field(description="Bonus for place 1, 2, ... of a problem")


class PlatformConfig(_Model):
    difficulties: Annotated[list[Difficulty], Field(min_length=1)]
    catalog: Catalog
    limits: Limits
    rate_limits: RateLimits
    legal: Legal
    rating: RatingFormula


class ConfigFileError(Exception):
    pass


def _read(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigFileError(f"{path}: {error}") from error


def load_platform_config(config_dir: Path) -> PlatformConfig:
    data = {
        "difficulties": _read(config_dir / DIFFICULTIES_FILE),
        "catalog": _read(config_dir / CATALOG_FILE),
        "limits": _read(config_dir / LIMITS_FILE),
        "rate_limits": _read(config_dir / RATE_LIMITS_FILE),
        "legal": _read(config_dir / LEGAL_FILE),
        "rating": _read(config_dir / RATING_FILE),
    }
    try:
        config = PlatformConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigFileError(f"{config_dir}: {error}") from error
    keys = [d.key for d in config.difficulties]
    if len(set(keys)) != len(keys):
        raise ConfigFileError(f"{config_dir / DIFFICULTIES_FILE}: duplicate keys")
    if sorted(config.rating.solved) != sorted(keys):
        raise ConfigFileError(
            f"{config_dir / RATING_FILE}: `solved` must name every difficulty level once"
            f" ({', '.join(keys)})"
        )
    return config
