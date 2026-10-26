"""Worker settings from environment variables (prefix `APX_`), see docs/configuration.md."""

import os
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt
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
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
