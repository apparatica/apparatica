"""Platform data from `config/*.yaml`: difficulty levels, the catalogue and limits, which the
frontend shows, and the rate limits against abuse, which it does not.

Loaded once at startup and validated strictly: a broken file stops the process instead of serving
a half-configured site.
"""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, ValidationError

DIFFICULTIES_FILE = "difficulties.yaml"
CATALOG_FILE = "catalog.yaml"
LIMITS_FILE = "limits.yaml"
RATE_LIMITS_FILE = "rate-limits.yaml"


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
    checks_per_ip: Window
    captcha: CaptchaRules


class PlatformConfig(_Model):
    difficulties: Annotated[list[Difficulty], Field(min_length=1)]
    catalog: Catalog
    limits: Limits
    rate_limits: RateLimits


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
    }
    try:
        config = PlatformConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigFileError(f"{config_dir}: {error}") from error
    keys = [d.key for d in config.difficulties]
    if len(set(keys)) != len(keys):
        raise ConfigFileError(f"{config_dir / DIFFICULTIES_FILE}: duplicate keys")
    return config
