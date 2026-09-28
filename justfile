set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# List workflows (color only in an interactive terminal, unless NO_COLOR is set).
default:
    @if [[ -t 1 && -z "${NO_COLOR+x}" ]]; then just --color always --list; else just --color never --list; fi

# Install the locked development and cloud dependencies.
[group('development')]
setup:
    uv sync --locked --group dev --extra cloud

# Serve the documentation with live reload.
[group('development')]
dev:
    uv run --group docs mkdocs serve

# Run a Python command in the project environment.
[group('development')]
run *args:
    uv run python {{args}}

# Verify the dependency lock and run the regression suite.
[group('checks')]
checks:
    uv lock --check
    just test

# Run all library tests; optional COMSOL tests skip when unavailable.
[group('checks')]
test:
    uv run --group dev pytest pydelling/tests -q

# Generate coverage and JUnit reports for CI.
[group('checks')]
test-ci:
    uv run --group dev pytest pydelling/tests --cov=pydelling --cov-report=xml --cov-report=html --cov-report=term-missing --junitxml=report.xml

alias coverage := test-ci
alias ci-test-reports := test-ci

# Build wheel and source distributions without changing the version.
[group('release')]
build:
    uv build

alias compile := build
alias wheel := build

# Refresh the dependency lock after an intentional dependency/version change.
[group('release')]
lock:
    uv lock

# Build strict documentation for deployment.
[group('release')]
docs-build:
    uv run --group docs mkdocs build --strict

# Build the development container.
[group('containers')]
container-build:
    docker compose build

# Start the development container.
[group('containers')]
up: container-build
    docker compose up -d

# Stop the development container.
[group('containers')]
down:
    docker compose down --remove-orphans

# Open a shell in the development container.
[group('containers')]
shell: up
    docker compose exec pydelling bash
