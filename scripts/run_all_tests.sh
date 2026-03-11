#!/usr/bin/env bash
# Run all Python service test suites.
# Usage: ./scripts/run_all_tests.sh [--coverage]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COVERAGE_FLAG=""
if [[ "${1:-}" == "--coverage" ]]; then
    COVERAGE_FLAG="--cov=. --cov-report=term-missing"
fi

SERVICES=(
    "activity-registry"
    "ape"
    "cvic"
    "entropy"
    "evidence-vault"
    "intent-extractor"
    "monitor"
    "parallel-auditing"
    "process-mining"
    "rlhc"
    "shadow-sop"
    "socket-interceptor"
    "trust-registry"
)

PASS=0
FAIL=0
SKIP=0

for svc in "${SERVICES[@]}"; do
    test_dir="$ROOT/$svc/tests"
    if [[ ! -d "$test_dir" ]]; then
        echo "⏭️  $svc — no tests/ directory, skipping"
        ((SKIP++))
        continue
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧪 $svc"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if (cd "$ROOT/$svc" && python3 -m pytest tests/ -q --tb=short $COVERAGE_FLAG 2>&1); then
        ((PASS++))
    else
        ((FAIL++))
        echo "❌ $svc FAILED"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ $FAIL -eq 0 ]]
