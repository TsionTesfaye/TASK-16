#!/bin/bash
# ReclaimOps test runner — Docker-only, deterministic, end-to-end.
#
# Stages:
#   1. Unit + integration/API tests (pytest inside the test-runner container)
#      with coverage gate: fail if total coverage < 90%.
#   2. Browser-driven E2E tests (Playwright) against a live backend
#      container on an isolated Docker network.
#
# Exit codes: 0 on full pass, non-zero on any failure.
set -euo pipefail

echo "=========================================="
echo "  ReclaimOps Test Suite (Docker)"
echo "=========================================="

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker is not installed or not on PATH." >&2
    exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "[ERROR] 'docker compose' plugin is required." >&2
    exit 2
fi

COMPOSE="docker compose"

cleanup() {
    set +e
    $COMPOSE --profile e2e down -v >/dev/null 2>&1
    $COMPOSE --profile test down -v >/dev/null 2>&1
}
trap cleanup EXIT

echo ""
echo "── Stage 1: Unit + integration/API tests (with coverage gate ≥90%) ──"
$COMPOSE --profile test build test-runner
$COMPOSE --profile test run --rm \
    --entrypoint "python -m pytest /unit_tests /API_tests --cov=/app/src --cov-report=term --cov-fail-under=95 --tb=short" \
    test-runner

echo ""
echo "── Stage 2: Playwright E2E tests (real browser) ──"
$COMPOSE --profile e2e build backend-e2e e2e-runner
$COMPOSE --profile e2e run --rm e2e-runner

echo ""
echo "=========================================="
echo "  All tests passed."
echo "=========================================="
