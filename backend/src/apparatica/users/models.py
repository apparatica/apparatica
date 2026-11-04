"""Tables of the own data of users: drafts of solutions (specs/04 §4, Ф2)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.core.db import Base


class Draft(Base):
    """The code of a problem the user is writing (FR-EDT-02): one per problem, the last save
    wins."""

    __tablename__ = "drafts"
    __table_args__ = (CheckConstraint("problem_version > 0", name="problem_version_positive"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"), primary_key=True)
    code: Mapped[str]
    problem_version: Mapped[int]  # the version the code is for (FR-PRB-05)
    updated_at: Mapped[datetime]
