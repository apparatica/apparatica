"""The journal of moderation (FR-ADM-03, specs/04 §4): every action of the admin panel with its
reason. A row outlives its actor and its target: the actor becomes null when the account is
deleted, the target is an id as text."""

import uuid
from datetime import datetime
from typing import Any, Literal, get_args

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apparatica.auth.models import User
from apparatica.core.db import Base, created_at, uuid_pk

ModerationAction = Literal["hide", "unhide", "set_role"]
TargetType = Literal["user", "submission"]


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class ModerationLog(Base):
    __tablename__ = "moderation_log"
    __table_args__ = (
        CheckConstraint(_one_of("action", get_args(ModerationAction)), name="action"),
        CheckConstraint(_one_of("target_type", get_args(TargetType)), name="target_type"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_given"),
        Index("ix_moderation_log_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Null: the account of the actor is deleted, or the action came from `apparatica-admin`.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    reason: Mapped[str]
    # What changed beyond the action, e.g. `{"from": "user", "to": "moderator"}` of `set_role`.
    details: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = created_at()

    # For the admin panel, which shows the nick of the actor.
    actor: Mapped[User | None] = relationship(viewonly=True, lazy="raise")
