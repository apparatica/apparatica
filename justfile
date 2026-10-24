# Entry point for development commands. Recipes work in sh (Linux, macOS, CI) and pwsh (Windows).

set windows-shell := ["pwsh.exe", "-NoLogo", "-NoProfile", "-Command"]

python := if os_family() == "windows" { "python" } else { "python3" }

# List available recipes
default:
    @just --list

# Install Python and JS dependencies and git hooks
install: install-py install-js
    pre-commit install

# Install Python dependencies of judge, backend, worker
install-py:
    poetry -C judge install
    poetry -C backend install
    poetry -C worker install

# Install JS dependencies of the pnpm workspace
install-js:
    pnpm install

# Run all linters and format checks
lint: lint-py lint-imports lint-js

# Lint Python and check its formatting
lint-py:
    poetry -P judge run ruff check .
    poetry -P judge run ruff format --check .

# Check architecture contracts (import-linter)
lint-imports:
    poetry -C judge run lint-imports
    poetry -C backend run lint-imports

# Lint JS/TS and check its formatting
lint-js:
    pnpm -C web lint
    pnpm -C web format:check

# Apply formatters and safe lint fixes
fmt:
    poetry -P judge run ruff check --fix .
    poetry -P judge run ruff format .
    pnpm -C web format

# Run strict type checks
typecheck:
    poetry -C judge run mypy
    poetry -C backend run mypy
    poetry -C worker run mypy
    poetry -C judge run mypy ../scripts

# Run all unit tests
test: test-py

# Run Python unit tests, including tests of repository scripts
test-py:
    poetry -C judge run pytest
    poetry -C backend run pytest
    poetry -C worker run pytest
    poetry -C judge run pytest ../scripts

# Check that lock files match pyproject.toml and agree on shared versions
check-locks:
    poetry -C judge check --lock
    poetry -C backend check --lock
    poetry -C worker check --lock
    {{ python }} scripts/check_locks.py

# Check dependency licenses against scripts/license-policy.toml
check-licenses: check-licenses-py check-licenses-js

# Check licenses of Python dependencies
check-licenses-py:
    poetry -C judge run python ../scripts/check_licenses.py python
    poetry -C backend run python ../scripts/check_licenses.py python
    poetry -C worker run python ../scripts/check_licenses.py python

# Check licenses of JS dependencies
check-licenses-js:
    pnpm licenses list --json -r | {{ python }} scripts/check_licenses.py js -

# Everything CI runs
check: check-locks check-licenses lint typecheck test
