"""Worker settings from environment variables (prefix `APX_`), see docs/configuration.md."""

import os
import socket
from pathlib import Path
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from judge.core.jobs import RESOURCE_CLASS_QUEUES


def _default_slots() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APX_", extra="ignore", frozen=True)

    queue_url: str = Field(
        default="redis://localhost:6379/0", description="valkey-queue: the Dramatiq broker"
    )
    queues: list[str] = Field(
        default=list(RESOURCE_CLASS_QUEUES.values()),
        description='Queues of the main slots, JSON: e.g. ["judge.heavy"] for a heavy pool',
    )
    slots: PositiveInt = Field(
        default_factory=_default_slots, description="Checks at once; half of the cores by default"
    )
    rejudge_slots: NonNegativeInt = Field(
        default=1, description="Extra slots for judge.rejudge (specs/07 §3); 0 takes no rejudges"
    )
    worker_id: str = Field(
        default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}",
        description="The value of the leases this worker holds",
    )

    # apx-sandboxd (ADR-0003): the worker never talks to Docker.
    sandboxd_socket: str = "/run/apx-sandboxd/sandboxd.sock"
    sandbox_runtime: Literal["runsc", "runc"] = Field(
        default="runsc", description="The runtime apx-sandboxd must use; runc only in development"
    )
    resource_classes: Path = Field(
        default=Path("config/resource-classes.yaml"), description="Limits of the sandboxes"
    )
    package_cache: Path = Field(
        default=Path("/var/cache/apparatica/packages"), description="Unpacked problem packages"
    )

    # Object storage (ADR-0013): the worker's key reads packages and writes artifacts.
    s3_endpoint_url: str | None = None
    s3_region: str = "garage"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket_packages: str = "packages"
    s3_bucket_artifacts: str = "artifacts"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
