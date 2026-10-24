# Entry point for development commands. Recipes work in sh (Linux, macOS, CI) and pwsh (Windows).

set windows-shell := ["pwsh.exe", "-NoLogo", "-NoProfile", "-Command"]

python := if os_family() == "windows" { "python" } else { "python3" }

# List available recipes
default:
    @just --list

# Install Python and JS dependencies and git hooks
install:
    poetry -C judge install
    poetry -C backend install
    poetry -C worker install
    pnpm install
    pre-commit install

# Run linters and format checks
lint:
    poetry -P judge run ruff check .
    poetry -P judge run ruff format --check .
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

# Run unit tests
test:
    poetry -C judge run pytest
    poetry -C backend run pytest
    poetry -C worker run pytest

# Check that lock files match pyproject.toml and agree on shared versions
check-locks:
    poetry -C judge check --lock
    poetry -C backend check --lock
    poetry -C worker check --lock
    {{ python }} scripts/check_locks.py

# Everything CI runs
check: check-locks lint typecheck test
