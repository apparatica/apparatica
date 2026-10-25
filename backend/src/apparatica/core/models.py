"""Tables of the core module (specs/04 §4)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.core.db import Base


class FeatureFlag(Base):
    """A deployment override of a flag declared in `apparatica.core.flags.FLAGS`."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(primary_key=True)
    enabled: Mapped[bool]
    # Targeting by role and share of users; evaluated once there are users (Ф2).
    rules: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
