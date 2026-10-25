"""Every table of the application: importing this module fills `Base.metadata` (Alembic, tests)."""

from apparatica.core import models as core_models
from apparatica.problems import models as problems_models
from apparatica.submissions import models as submissions_models

__all__ = ["core_models", "problems_models", "submissions_models"]
