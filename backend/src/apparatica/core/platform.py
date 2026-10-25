"""Platform data from `config/*.yaml` that the frontend shows: difficulty levels and limits.

Loaded once at startup and validated strictly: a broken file stops the process instead of serving
a half-configured site.
"""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, ValidationError

DIFFICULTIES_FILE = "difficulties.yaml"
LIMITS_FILE = "limits.yaml"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Difficulty(_Model):
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    title: str
    token: Annotated[
        str, Field(description="Colour pair of the design tokens, e.g. e for --e/--es")
    ]


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


class Limits(_Model):
    solution: SolutionLimits
    quotas: Quotas


class PlatformConfig(_Model):
    difficulties: Annotated[list[Difficulty], Field(min_length=1)]
    limits: Limits


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
        "limits": _read(config_dir / LIMITS_FILE),
    }
    try:
        config = PlatformConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigFileError(f"{config_dir}: {error}") from error
    keys = [d.key for d in config.difficulties]
    if len(set(keys)) != len(keys):
        raise ConfigFileError(f"{config_dir / DIFFICULTIES_FILE}: duplicate keys")
    return config
