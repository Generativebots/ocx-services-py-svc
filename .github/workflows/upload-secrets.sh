#!/bin/bash
# =============================================================================
# OCX Python Services — Upload GitHub Secrets
# =============================================================================
# Usage: bash .github/workflows/upload-secrets.sh [env]
#   env = dev, test, prod, or all (default: menu)
# Prerequisites: gh auth login
# Blank input = skip (never overwrites existing values)
# =============================================================================
set -e

REPO="Generativebots/ocx-services-py-svc"

# ── Helpers ──────────────────────────────────────────────────────────────────
secret_exists() {
  gh secret list --env "$2" -R "$1" 2>/dev/null | grep -q "^${3}\b"
}
var_exists() {
  gh variable list --env "$2" -R "$1" 2>/dev/null | grep -q "^${3}\b"
}
set_secret() {
  local env=$1 key=$2 value=$3
  echo "  ✅ $key"
  echo "$value" | gh secret set "$key" --env "$env" -R "$REPO"
}
set_var() {
  local env=$1 key=$2 value=$3
  if var_exists "$REPO" "$env" "$key"; then
    echo "  ⏭️  $key (var) — already exists"
  else
    echo "  ✅ $key (var)"
    gh variable set "$key" --env "$env" -R "$REPO" --body "$value"
  fi
}
ask_secret() {
  local env=$1 key=$2
  if secret_exists "$REPO" "$env" "$key"; then
    echo "  ⏭️  $key — already exists (blank=keep)"
  fi
  read -sp "  $key: " value && echo ""
  if [ -n "$value" ]; then
    set_secret "$env" "$key" "$value"
  else
    echo "    kept existing / skipped"
  fi
}

# ── Secrets ──────────────────────────────────────────────────────────────────
# GCP_PROJECT_ID, GCP_SA_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY,
# POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD
# ─────────────────────────────────────────────────────────────────────────────
SECRETS=("GCP_PROJECT_ID" "GCP_SA_KEY" "SUPABASE_URL" "SUPABASE_SERVICE_KEY" "POSTGRES_HOST" "POSTGRES_USER" "POSTGRES_PASSWORD")

upload_env() {
  local env=$1
  gh api -X PUT "repos/$REPO/environments/$env" --silent 2>/dev/null || true

  echo "=========================================="
  echo "  📦 Environment: $env"
  echo "=========================================="
  echo "  Blank = keep existing / skip"
  echo ""

  for secret in "${SECRETS[@]}"; do
    ask_secret "$env" "$secret"
  done

  set_var "$env" "POSTGRES_DB" "postgres"
  set_var "$env" "POSTGRES_PORT" "5432"
  echo ""
}

# ── Environment Selection ───────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  OCX Python Services — Secret Upload"
echo "=========================================="

if [ -n "$1" ]; then
  SELECTED="$1"
else
  echo ""
  echo "  Which environment?"
  echo "  1) dev"
  echo "  2) test"
  echo "  3) prod"
  echo "  4) all"
  echo ""
  read -p "  Select [1-4]: " choice
  case $choice in
    1) SELECTED="dev" ;;
    2) SELECTED="test" ;;
    3) SELECTED="prod" ;;
    4) SELECTED="all" ;;
    *) echo "Invalid choice"; exit 1 ;;
  esac
fi

echo ""

case $SELECTED in
  dev)  upload_env "dev" ;;
  test) upload_env "test" ;;
  prod) upload_env "prod" ;;
  all)
    upload_env "dev"
    upload_env "test"
    upload_env "prod"
    ;;
  *) echo "Invalid env: $SELECTED"; exit 1 ;;
esac

echo "✅ Python Services secrets done!"
