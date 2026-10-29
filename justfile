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
    pnpm -C e2e format:check

# Apply formatters and safe lint fixes
fmt:
    poetry -P judge run ruff check --fix .
    poetry -P judge run ruff format .
    pnpm -C web format
    pnpm -C e2e format

# Run strict type checks
typecheck: typecheck-py typecheck-js

# Type-check Python (mypy, strict)
typecheck-py:
    poetry -C judge run mypy
    poetry -C backend run mypy
    poetry -C worker run mypy
    poetry -C judge run mypy ../scripts
    poetry -C judge run mypy --platform linux ../toolchain/apx-run ../toolchain/apx-init ../toolchain/tests

# Type-check TypeScript (tsc, strict)
typecheck-js:
    pnpm -C web typecheck
    pnpm -C e2e typecheck

# Run all unit tests
test: test-py test-js

# Run Python unit tests, including tests of repository scripts
test-py:
    poetry -C judge run pytest
    poetry -C backend run pytest
    poetry -C worker run pytest
    poetry -C judge run pytest ../scripts

# Run frontend tests (Vitest, MSW) and the checks of the waveview site that need no build
test-js:
    pnpm -C web test
    pnpm -C waveview test

# Build the frontend for production (next build)
build-js:
    pnpm -C web build

# Storybook of the domain components (http://localhost:6006; docs/frontend.md)
storybook:
    pnpm -C web storybook

# Build the static Storybook into web/storybook-static
build-storybook:
    pnpm -C web build-storybook

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

# Record the submission scenarios of the mocks (all or the named) in the toolchain image
record-scenarios *names:
    poetry -C judge run python ../scripts/record_scenarios.py {{ names }}

# Write the demo problems of the mocks from problems/ (web/src/mocks/problem-versions.json)
mock-problems:
    poetry -C judge run python ../scripts/mock_problems.py

# Run the frontend on the mock API, without the backend (http://localhost:3000; docs/frontend.md)
dev-mocks $NEXT_PUBLIC_API_MOCKING="enabled":
    pnpm -C web dev

# Validate every problem package in the toolchain image, with the determinism and statement
# checks of CI
validate-problems:
    poetry -C judge run judge validate --determinism --statement-check "pnpm -C ../web --silent statement:check" ../problems

# Everything CI runs (the toolchain image has its own workflow: toolchain-build, toolchain-test)
check: check-locks check-licenses check-api lint typecheck test

compose := "docker compose -f deploy/compose.yaml -f deploy/compose.dev.yaml"

# Start the stand: build the images, migrate, set up Garage, register the toolchain profile, start
# the worker, import the demo problems (http://localhost:8080; docs/stand.md). `up --wait` fails on
# finished one-shot services, so it waits for the long-running ones, and the import runs in the
# foreground with its exit code.
up:
    {{ compose }} up -d --build --wait caddy valkey-queue valkey-cache ingest worker
    {{ compose }} run --rm demo-problems

# Stop the stand; the data volumes stay (remove them with: docker compose ... down -v)
down:
    {{ compose }} down

# Follow the logs of the stand, or of the given services
logs *services:
    {{ compose }} logs -f {{ services }}

# Check the running stand: the object storage (key permissions, presigned URLs, CORS, website) and
# the judging of a guest's submissions through Caddy
stand-check:
    {{ compose }} run --rm storage-check
    {{ compose }} run --rm judge-check

# End-to-end tests against the running stand with a real worker: Playwright and axe (docs/stand.md).
# E2E_BASE_URL: the site (http://localhost:8080); E2E_BROWSER: the Playwright channel of an installed
# browser (chrome by default, msedge on Windows)
e2e *args:
    pnpm -C e2e test {{ args }}

toolchain_image := "apparatica-toolchain:dev"
# Base image override for networks without Docker Hub access; keep the digest from the Dockerfile,
# e.g. TOOLCHAIN_BASE_IMAGE=mirror.gcr.io/library/debian@sha256:<digest>
toolchain_base := env("TOOLCHAIN_BASE_IMAGE", "")
# Debian mirror override for slow networks, e.g. TOOLCHAIN_DEBIAN_MIRROR=http://mirror.yandex.ru/debian
toolchain_mirror := env("TOOLCHAIN_DEBIAN_MIRROR", "")

# Build the sandbox toolchain image
toolchain-build:
    docker build {{ if toolchain_base != "" { "--build-arg BASE_IMAGE=" + toolchain_base } else { "" } }} {{ if toolchain_mirror != "" { "--build-arg DEBIAN_MIRROR=" + toolchain_mirror } else { "" } }} -t {{ toolchain_image }} toolchain

# Run the toolchain image tests and the worker's sandbox tests against the image (specs/07 §5)
toolchain-test:
    poetry -C judge run pytest ../toolchain/tests -v
    poetry -C worker run pytest -m image -v

waveview_image := "apparatica-waveview:dev"
# Base image overrides for networks without Docker Hub access; keep the digests from the Dockerfile,
# e.g. WAVEVIEW_RUST_IMAGE=mirror.gcr.io/library/rust:1.95-trixie@sha256:<digest>
waveview_rust := env("WAVEVIEW_RUST_IMAGE", "")
waveview_runtime := env("WAVEVIEW_RUNTIME_IMAGE", "")
waveview_args := (if waveview_rust != "" { "--build-arg RUST_IMAGE=" + waveview_rust } else { "" }) + " " + (if waveview_runtime != "" { "--build-arg RUNTIME_IMAGE=" + waveview_runtime } else { "" })

# Build the waveview site image (docs/waveview.md) and its files in waveview/dist for the test
waveview-build:
    docker build {{ waveview_args }} -t {{ waveview_image }} waveview
    docker build {{ waveview_args }} --target export -o waveview/dist waveview

# Open the built viewer in a browser through the adapter (WAVEVIEW_BROWSER: chrome, msedge)
waveview-test:
    pnpm -C waveview test:build

# Serve the built viewer (waveview/dist) to the problem page of `just dev-mocks`; start dev-mocks
# with NEXT_PUBLIC_MOCK_WAVEVIEW_URL=http://localhost:<port>/<version>/index.html (docs/frontend.md)
waveview-serve port="3901" origin="http://localhost:3000":
    node waveview/tests/serve.mjs waveview/dist {{ port }} {{ origin }}
