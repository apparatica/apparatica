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
typecheck: typecheck-py typecheck-js

# Type-check Python (mypy, strict)
typecheck-py:
    poetry -C judge run mypy
    poetry -C backend run mypy
    poetry -C worker run mypy
    poetry -C judge run mypy ../scripts
    poetry -C judge run mypy --platform linux ../toolchain/apx-run ../toolchain/tests

# Type-check TypeScript (tsc, strict)
typecheck-js:
    pnpm -C web typecheck

# Run all unit tests
test: test-py test-js

# Run Python unit tests, including tests of repository scripts
test-py:
    poetry -C judge run pytest
    poetry -C backend run pytest
    poetry -C worker run pytest
    poetry -C judge run pytest ../scripts

# Run frontend tests (Vitest, MSW)
test-js:
    pnpm -C web test

# Build the frontend for production (next build)
build-js:
    pnpm -C web build

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

# Regenerate generated contracts: JSON Schemas of problem.yaml and of testbench result records
# (tests check that they are current)
schemas:
    poetry -C judge run judge schema problem --output schemas/problem.schema.json
    poetry -C judge run judge schema tb-result --output schemas/tb-result.schema.json

# Regenerate the API contract: backend/openapi.json from the code, then the TS client types
# (specs/05 §0; a backend test and `just check-api` check that both are current)
openapi:
    poetry -C backend run apparatica openapi --output openapi.json --config-dir ../config
    pnpm -C web api:generate

# Check that the TS client types match backend/openapi.json
check-api:
    pnpm -C web api:check

# Validate every problem package in the toolchain image, with the determinism check of CI
validate-problems:
    poetry -C judge run judge validate --determinism ../problems

# Everything CI runs (the toolchain image has its own workflow: toolchain-build, toolchain-test)
check: check-locks check-licenses check-api lint typecheck test

toolchain_image := "apparatica-toolchain:dev"
# Base image override for networks without Docker Hub access; keep the digest from the Dockerfile,
# e.g. TOOLCHAIN_BASE_IMAGE=mirror.gcr.io/library/debian@sha256:<digest>
toolchain_base := env("TOOLCHAIN_BASE_IMAGE", "")
# Debian mirror override for slow networks, e.g. TOOLCHAIN_DEBIAN_MIRROR=http://mirror.yandex.ru/debian
toolchain_mirror := env("TOOLCHAIN_DEBIAN_MIRROR", "")

# Build the sandbox toolchain image
toolchain-build:
    docker build {{ if toolchain_base != "" { "--build-arg BASE_IMAGE=" + toolchain_base } else { "" } }} {{ if toolchain_mirror != "" { "--build-arg DEBIAN_MIRROR=" + toolchain_mirror } else { "" } }} -t {{ toolchain_image }} toolchain

# Run the toolchain image tests: pytest on the host, commands in a sandboxed container (specs/07 §5.1)
toolchain-test:
    poetry -C judge run pytest ../toolchain/tests -v
