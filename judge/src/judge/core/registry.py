"""Language modules by the `language` key of problem.yaml (ADR-0011).

A language module registers itself under the entry point group below; the core never imports
`judge.languages` directly (import-linter contract).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib.metadata import entry_points

from judge.core.stage import Stage

ENTRY_POINT_GROUP = "apparatica.judge.languages"


@dataclass(frozen=True)
class LanguageModule:
    name: str
    stages: Mapping[str, type[Stage]]  # stage type -> plugin class


class UnknownLanguageError(LookupError):
    pass


@cache
def get_language(name: str) -> LanguageModule:
    found = entry_points(group=ENTRY_POINT_GROUP, name=name)
    if not found:
        raise UnknownLanguageError(
            f"no language module {name!r} (entry points {ENTRY_POINT_GROUP})"
        )
    module = next(iter(found)).load()
    if not isinstance(module, LanguageModule) or module.name != name:
        raise TypeError(f"entry point {name!r} must be a LanguageModule named {name!r}")
    return module
