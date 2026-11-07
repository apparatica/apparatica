"""Every table of the application: importing this module fills `Base.metadata` (Alembic, tests)."""

from apparatica.admin import models as admin_models
from apparatica.auth import models as auth_models
from apparatica.core import models as core_models
from apparatica.leaderboards import models as leaderboards_models
from apparatica.problems import models as problems_models
from apparatica.submissions import models as submissions_models
from apparatica.users import models as users_models

__all__ = [
    "admin_models",
    "auth_models",
    "core_models",
    "leaderboards_models",
    "problems_models",
    "submissions_models",
    "users_models",
]
