"""Check dependency licenses against scripts/license-policy.toml (NFR-MAINT-07, ADR-0012).

Usage:
    python check_licenses.py python          # inside a Poetry environment: installed distributions
    python check_licenses.py js <file | ->   # output of `pnpm licenses list --json -r`
"""

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import distributions
from pathlib import Path
from typing import Any

POLICY_PATH = Path(__file__).resolve().parent / "license-policy.toml"
TOKEN_RE = re.compile(r"\(|\)|[^\s()]+")


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    name: str
    version: str
    license: str | None


@dataclass(frozen=True)
class Policy:
    allowed: frozenset[str]
    aliases: dict[str, str]
    exceptions: frozenset[tuple[str, str]]

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> "Policy":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        exceptions = data.get("exceptions", [])
        for entry in exceptions:
            if not entry.get("adr"):
                raise ValueError(f"License exception {entry.get('name')!r} must cite an ADR")
        return cls(
            allowed=frozenset(data["allowed"]),
            aliases=dict(data.get("aliases", {})),
            exceptions=frozenset((e["ecosystem"], canonical_name(e["name"])) for e in exceptions),
        )

    def normalize(self, license_name: str) -> str:
        license_name = license_name.strip()
        return self.aliases.get(license_name, license_name)

    def is_allowed(self, expression: str) -> bool:
        """Evaluate an SPDX license expression. Raises ValueError if it cannot be parsed."""
        parser = _ExpressionParser(TOKEN_RE.findall(self.normalize(expression)), self.allowed)
        return parser.parse()


class _ExpressionParser:
    """Recursive descent over `expr := term (OR term)*; term := factor (AND factor)*;
    factor := "(" expr ")" | id [WITH id]`. An expression is allowed if it can be satisfied."""

    def __init__(self, tokens: list[str], allowed: frozenset[str]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.allowed = allowed

    def parse(self) -> bool:
        if not self.tokens:
            raise ValueError("empty license expression")
        result = self._expr()
        if self.pos != len(self.tokens):
            raise ValueError(f"unexpected token {self.tokens[self.pos]!r}")
        return result

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise ValueError("unexpected end of license expression")
        self.pos += 1
        return token

    def _keyword(self, word: str) -> bool:
        token = self._peek()
        if token is not None and token.upper() == word:
            self.pos += 1
            return True
        return False

    def _expr(self) -> bool:
        result = self._term()
        while self._keyword("OR"):
            result = self._term() or result
        return result

    def _term(self) -> bool:
        result = self._factor()
        while self._keyword("AND"):
            result = self._factor() and result
        return result

    def _factor(self) -> bool:
        token = self._take()
        if token == "(":
            result = self._expr()
            if self._take() != ")":
                raise ValueError("missing ')'")
            return result
        if token == ")" or token.upper() in {"AND", "OR", "WITH"}:
            raise ValueError(f"unexpected token {token!r}")
        if self._keyword("WITH"):
            self._take()  # License exceptions only add permissions.
        return token in self.allowed


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_license(
    expression: str | None, license_field: str | None, classifiers: list[str], policy: Policy
) -> str | None:
    """Pick the most reliable license declaration from Python package metadata."""
    if expression:
        return expression
    names = [
        policy.normalize(c.rsplit(" :: ", 1)[-1])
        for c in classifiers
        if c.startswith("License :: ") and c != "License :: OSI Approved"
    ]
    if names:
        return " OR ".join(names)
    # The free-form License field often holds the whole license text; trust it only if short.
    if license_field and "\n" not in license_field.strip() and len(license_field) <= 64:
        return license_field
    return None


def collect_python(policy: Policy) -> list[Dependency]:
    return [
        Dependency(
            ecosystem="python",
            name=canonical_name(dist.metadata["Name"]),
            version=dist.version,
            license=python_license(
                dist.metadata.get("License-Expression"),
                dist.metadata.get("License"),
                dist.metadata.get_all("Classifier") or [],
                policy,
            ),
        )
        for dist in distributions()
    ]


def collect_js(report: dict[str, list[dict[str, Any]]]) -> list[Dependency]:
    return [
        Dependency(
            ecosystem="js",
            name=package["name"],
            version=", ".join(package.get("versions", [])),
            license=None if license_name == "Unknown" else package.get("license", license_name),
        )
        for license_name, packages in report.items()
        for package in packages
    ]


def find_violations(dependencies: list[Dependency], policy: Policy) -> list[str]:
    violations = []
    for dep in sorted(dependencies, key=lambda d: d.name):
        if (dep.ecosystem, canonical_name(dep.name)) in policy.exceptions:
            continue
        label = f"{dep.ecosystem}: {dep.name} {dep.version}"
        if dep.license is None:
            violations.append(f"{label}: license not declared")
            continue
        try:
            allowed = policy.is_allowed(dep.license)
        except ValueError as error:
            violations.append(f"{label}: cannot parse license {dep.license!r} ({error})")
            continue
        if not allowed:
            violations.append(f"{label}: license {dep.license!r} is not allowed")
    return violations


def main(argv: list[str]) -> int:
    policy = Policy.load()
    match argv:
        case ["python"]:
            dependencies = collect_python(policy)
        case ["js", source]:
            text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
            dependencies = collect_js(json.loads(text))
        case _:
            print(__doc__, file=sys.stderr)
            return 2

    violations = find_violations(dependencies, policy)
    if violations:
        print("Dependencies with disallowed or unknown licenses:", file=sys.stderr)
        print("\n".join(f"  {v}" for v in violations), file=sys.stderr)
        print(f"Policy: {POLICY_PATH.name}; exceptions require an ADR.", file=sys.stderr)
        return 1
    print(f"Licenses OK: {len(dependencies)} {argv[0]} packages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
