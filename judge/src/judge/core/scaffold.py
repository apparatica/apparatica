"""`judge new`: a new problem package from the language module's template (specs/06 §5)."""

import re
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml

from judge.core.package import MANIFEST_NAME
from judge.core.registry import LanguageModule

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class ScaffoldError(ValueError):
    pass


def top_name(slug: str) -> str:
    """The module name for a slug: `sync-fifo` -> `sync_fifo`, `4bit-adder` -> `m_4bit_adder`."""
    name = slug.replace("-", "_")
    return name if name[0].isalpha() else f"m_{name}"


def next_number(problems_dir: Path) -> int:
    """The catalogue number after the largest one among the packages next to the new one."""
    numbers = [0]
    for manifest in problems_dir.glob(f"*/{MANIFEST_NAME}"):
        try:
            number = yaml.safe_load(manifest.read_text(encoding="utf-8")).get("number")
        except (OSError, UnicodeDecodeError, yaml.YAMLError, AttributeError):
            continue
        if isinstance(number, int):
            numbers.append(number)
    return max(numbers) + 1


def _copy(template: Traversable, target: Path, substitutions: dict[str, str]) -> list[Path]:
    written = []
    for item in sorted(template.iterdir(), key=lambda t: t.name):
        if item.name.startswith(".") or item.name == "__pycache__":
            continue
        name = item.name
        for placeholder, value in substitutions.items():
            name = name.replace(placeholder, value)
        destination = target / name
        if item.is_dir():
            destination.mkdir()
            written += _copy(item, destination, substitutions)
            continue
        text = item.read_text(encoding="utf-8")
        for placeholder, value in substitutions.items():
            text = text.replace(placeholder, value)
        destination.write_text(text, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def create_package(language: LanguageModule, problems_dir: Path, slug: str) -> list[Path]:
    """Create `problems_dir/<slug>` from the template; returns the files written."""
    if not SLUG.match(slug) or len(slug) > 64:
        raise ScaffoldError(f"{slug!r} is not a slug: lower-case letters, digits and hyphens")
    if language.package_template is None:
        raise ScaffoldError(f"language {language.name} has no package template")
    target = problems_dir / slug
    if target.exists():
        raise ScaffoldError(f"{target} already exists")
    substitutions = {
        "__slug__": slug,
        "__top__": top_name(slug),
        "__number__": str(next_number(problems_dir)),
    }
    target.mkdir(parents=True)
    return _copy(language.package_template, target, substitutions)
