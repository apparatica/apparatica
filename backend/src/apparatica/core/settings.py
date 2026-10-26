"""Process settings from environment variables (prefix `APX_`), see docs/configuration.md.

Settings that differ between deployments live here; data that the frontend shows (difficulty
levels, quotas) lives in `config/*.yaml` and is loaded by `apparatica.core.platform`.
"""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveFloat, PositiveInt, SecretStr
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
    s3_bucket_artifacts: str = "artifacts"

    # valkey-queue (ADR-0002): the Dramatiq broker, queue positions. Required in production; unset
    # elsewhere means no workers: a submission stays queued.
    queue_url: str | None = Field(default=None, description="redis:// URL of valkey-queue")

    # Job tokens (specs/07 §5.3): the API signs them, the ingestor checks them. Required in
    # production; elsewhere an unset key means a random key of the process.
    job_token_key: SecretStr | None = Field(default=None, min_length=32)
    job_token_ttl_s: PositiveInt = Field(
        default=86400, description="Lifetime of a job token: queue wait and every attempt"
    )

    # valkey-cache: rate limits against abuse (NFR-SEC-06). Required in production; unset elsewhere
    # means counters in the memory of the process.
    cache_url: str | None = Field(default=None, description="redis:// URL of valkey-cache")

    # Guests (ADR-0010): the signed cookie `ap_guest`, the salted hash of client addresses
    # (NFR-PRIV-01) and the captcha. Required in production; elsewhere an unset key means a random
    # key of the process: its guests are forgotten on restart.
    guest_cookie_key: SecretStr | None = Field(default=None, min_length=32)
    ip_hash_salt: SecretStr | None = Field(default=None, min_length=32)
    captcha_key: SecretStr | None = Field(
        default=None, min_length=32, description="HMAC key of ALTCHA challenges"
    )
    cookie_secure: bool = Field(
        default=True, description="Secure cookies; off only for a stand served over plain HTTP"
    )

    # The ingestor (`apparatica ingest`, ADR-0009): its consumer in the group of judge:results.
    ingest_consumer: str | None = Field(
        default=None, description="Consumer name; unset means <hostname>:<pid>"
    )
    watchdog_grace_s: PositiveFloat = Field(
        default=300,
        description="The watchdog waits this long beyond the limits of every attempt",
    )


@cache
def get_settings() -> Settings:
    return Settings()
