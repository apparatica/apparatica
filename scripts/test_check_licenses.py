import pytest

from check_licenses import Dependency, Policy, collect_js, find_violations, python_license


@pytest.fixture
def policy() -> Policy:
    return Policy(
        allowed=frozenset({"MIT", "Apache-2.0", "GPL-3.0-or-later"}),
        aliases={"MIT License": "MIT"},
        exceptions=frozenset({("toolchain", "nangate45"), ("python", "odd-package")}),
    )


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT", True),
        ("BSD-4-Clause", False),
        ("MIT OR BSD-4-Clause", True),
        ("BSD-4-Clause OR MIT", True),
        ("MIT AND BSD-4-Clause", False),
        ("MIT AND Apache-2.0", True),
        ("(MIT OR BSD-4-Clause) AND Apache-2.0", True),
        ("BSD-4-Clause OR (MIT AND SSPL-1.0)", False),
        ("GPL-3.0-or-later WITH GCC-exception-3.1", True),
        ("mit", False),  # identifiers are case-sensitive
        ("BSD-4-Clause or Apache-2.0", True),  # operators are not
        ("MIT License", True),  # alias
    ],
)
def test_is_allowed(policy: Policy, expression: str, expected: bool) -> None:
    assert policy.is_allowed(expression) is expected


@pytest.mark.parametrize("expression", ["", "MIT OR", "(MIT", "MIT)", "AND MIT", "Apache 2.0"])
def test_is_allowed_rejects_malformed_expressions(policy: Policy, expression: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        policy.is_allowed(expression)


def test_python_license_prefers_expression(policy: Policy) -> None:
    classifiers = ["License :: OSI Approved :: MIT License"]
    assert python_license("Apache-2.0", "MIT", classifiers, policy) == "Apache-2.0"


def test_python_license_uses_classifiers(policy: Policy) -> None:
    classifiers = [
        "License :: OSI Approved",
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
    ]
    assert python_license(None, None, classifiers, policy) == "MIT OR Apache Software License"


def test_python_license_ignores_long_license_text(policy: Policy) -> None:
    assert python_license(None, "MIT", [], policy) == "MIT"
    assert python_license(None, "Copyright (c)\n\nPermission is granted...", [], policy) is None


def test_find_violations(policy: Policy) -> None:
    dependencies = [
        Dependency("python", "ok", "1.0", "MIT"),
        Dependency("python", "Odd_Package", "1.0", None),  # excepted
        Dependency("python", "missing", "1.0", None),
        Dependency("js", "proprietary", "2.0", "SSPL-1.0"),
        Dependency("js", "broken", "3.0", "MIT OR"),
    ]
    assert find_violations(dependencies, policy) == [
        "js: broken 3.0: cannot parse license 'MIT OR' (unexpected end of license expression)",
        "python: missing 1.0: license not declared",
        "js: proprietary 2.0: license 'SSPL-1.0' is not allowed",
    ]


def test_collect_js_marks_unknown_licenses() -> None:
    report = {
        "MIT": [{"name": "a", "versions": ["1.0.0"], "license": "MIT"}],
        "Unknown": [{"name": "b", "versions": ["2.0.0"], "license": "Unknown"}],
    }
    assert collect_js(report) == [
        Dependency("js", "a", "1.0.0", "MIT"),
        Dependency("js", "b", "2.0.0", None),
    ]


def test_repository_policy_is_valid() -> None:
    policy = Policy.load()
    assert "AGPL-3.0-or-later" in policy.allowed
    assert "GPL-2.0-only" not in policy.allowed
    assert ("toolchain", "nangate45") in policy.exceptions
