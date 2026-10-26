"""How long the artifacts of a check are kept (specs/07 §4.4): `config/retention.yaml`."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apparatica.core.platform import ConfigFileError
from judge.core.jobs import ArtifactKind
from judge.core.stage import SubmissionKind

RETENTION_FILE = "retention.yaml"

Days = Annotated[int, Field(gt=0)] | None  # None: kept


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class KindRetention(_Model):
    log: Days
    events: Days
    fst: Days
    tb_result: Days


class Retention(_Model):
    run: KindRetention
    submit: KindRetention

    def expires_at(
        self, submission: SubmissionKind, artifact: ArtifactKind, stored: datetime
    ) -> datetime | None:
        days: int | None = getattr(getattr(self, submission), artifact)
        return None if days is None else stored + timedelta(days=days)


def load_retention(config_dir: Path) -> Retention:
    path = config_dir / RETENTION_FILE
    try:
        return Retention.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigFileError(f"{path}: {error}") from error
