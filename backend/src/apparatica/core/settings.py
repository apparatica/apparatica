"""Process settings from environment variables (prefix `APX_`), see docs/configuration.md.

Settings that differ between deployments live here; data that the frontend shows (difficulty
levels, quotas) lives in `config/*.yaml` and is loaded by `apparatica.core.platform`.
"""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveFloat, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APX_", extra="ignore", frozen=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://apparatica:apparatica@localhost:5432/apparatica",
        description="SQLAlchemy URL with an async driver",
    )
    config_dir: Path = Field(
        default=Path("config"), description="Directory with difficulties.yaml and limits.yaml"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
    feature_flags_ttl_s: PositiveFloat = Field(
        default=30, description="In-process cache of feature flags (specs/03 §7)"
    )
    health_timeout_s: PositiveFloat = 2

    # Object storage (ADR-0013): any S3 API, Garage in docker compose.
    s3_endpoint_url: str | None = Field(
        default=None, description="S3 API endpoint; unset means AWS itself"
    )
    s3_region: str = "garage"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket_packages: str = "packages"


@cache
def get_settings() -> Settings:
    return Settings()
