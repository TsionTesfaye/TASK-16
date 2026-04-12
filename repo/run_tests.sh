#!/bin/bash
set -e

echo "=========================================="
echo "  ReclaimOps Data Layer Tests"
echo "=========================================="

docker compose build test-runner
docker compose run --rm test-runner

echo ""
echo "=========================================="
echo "  All tests passed."
echo "=========================================="
