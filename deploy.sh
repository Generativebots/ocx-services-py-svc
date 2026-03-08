#!/bin/bash
# =============================================================================
# OCX Python Services — Cloud Run Deployment Script
# =============================================================================
# Usage: ./deploy.sh [service] [env] [region]
#   service: trust-registry | jury | ledger | activity-registry |
#            evidence-vault | authority | process-mining | all
#   env:     dev | test | prod (default: dev)
#   region:  us-central1 (default)
#
# Required env vars:
#   PROJECT_ID, SUPABASE_URL, SUPABASE_SERVICE_KEY
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Args
SERVICE=${1:-all}
DEPLOY_ENV=${2:-dev}
REGION=${3:-us-central1}

# ── Validate ──────────────────────────────────────────────────────────────────
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: PROJECT_ID not set${NC}"
    echo "Export it: export PROJECT_ID=your-project-id"
    exit 1
fi
if [ -z "$SUPABASE_URL" ]; then echo -e "${RED}Error: SUPABASE_URL not set${NC}"; exit 1; fi
if [ -z "$SUPABASE_SERVICE_KEY" ]; then echo -e "${RED}Error: SUPABASE_SERVICE_KEY not set${NC}"; exit 1; fi

# ── Profile Settings ─────────────────────────────────────────────────────────
case "$DEPLOY_ENV" in
  prod)
    MIN_INSTANCES=1;  MAX_INSTANCES=5;  MEMORY=2Gi;  CPU=2
    INGRESS=internal-and-cloud-load-balancing
    ENV_SUFFIX=""
    echo -e "${CYAN}━━━ 🚀 PRODUCTION ━━━${NC}"
    ;;
  test)
    MIN_INSTANCES=1;  MAX_INSTANCES=3;  MEMORY=2Gi;  CPU=2
    INGRESS=internal-and-cloud-load-balancing
    ENV_SUFFIX="-test"
    echo -e "${CYAN}━━━ 🧪 TEST/STAGING ━━━${NC}"
    ;;
  *)
    MIN_INSTANCES=1;  MAX_INSTANCES=3;  MEMORY=2Gi;  CPU=2
    INGRESS=internal-and-cloud-load-balancing
    ENV_SUFFIX="-dev"
    DEPLOY_ENV="dev"
    echo -e "${CYAN}━━━ 🛠️  DEV ━━━${NC}"
    ;;
esac

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}OCX Python Services Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo "  Project:      $PROJECT_ID"
echo "  Region:       $REGION"
echo "  Environment:  $DEPLOY_ENV"
echo "  Service:      $SERVICE"
echo "  Instances:    $MIN_INSTANCES → $MAX_INSTANCES"
echo "  Memory:       $MEMORY | CPU: $CPU"
echo "  Ingress:      $INGRESS"
echo -e "${GREEN}========================================${NC}"
echo ""

# Enable required APIs
echo -e "${YELLOW}Enabling Cloud APIs...${NC}"
gcloud services enable run.googleapis.com --project=$PROJECT_ID

# ── Deploy Function ───────────────────────────────────────────────────────────
deploy_service() {
    local BASE_NAME=$1
    local SERVICE_DIR=$2
    local PORT=${3:-8001}
    local SVC_NAME="${BASE_NAME}${ENV_SUFFIX}"

    echo -e "${YELLOW}Deploying ${SVC_NAME} [$DEPLOY_ENV]...${NC}"

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    cd "$SCRIPT_DIR/$SERVICE_DIR"

    gcloud run deploy "$SVC_NAME" \
        --source . \
        --region=$REGION \
        --project=$PROJECT_ID \
        --platform=managed \
        --no-allow-unauthenticated \
        --ingress=$INGRESS \
        --set-env-vars="SUPABASE_URL=$SUPABASE_URL,SUPABASE_SERVICE_KEY=$SUPABASE_SERVICE_KEY,OCX_ENV=$DEPLOY_ENV" \
        --memory=$MEMORY \
        --cpu=$CPU \
        --min-instances=$MIN_INSTANCES \
        --max-instances=$MAX_INSTANCES

    SERVICE_URL=$(gcloud run services describe "$SVC_NAME" --region=$REGION --project=$PROJECT_ID --format='value(status.url)')
    echo -e "${GREEN}✅ $SVC_NAME deployed: $SERVICE_URL${NC}"
    cd "$SCRIPT_DIR"
}

# ── Router ────────────────────────────────────────────────────────────────────
case $SERVICE in
    trust-registry)
        deploy_service "ocx-trust-registry" "trust-registry" 8001
        ;;
    jury)
        deploy_service "ocx-jury" "jury" 8002
        ;;
    ledger)
        deploy_service "ocx-ledger" "ledger" 8003
        ;;
    activity-registry)
        deploy_service "ocx-activity-registry" "activity-registry" 8004
        ;;
    evidence-vault)
        deploy_service "ocx-evidence-vault" "evidence-vault" 8005
        ;;
    authority)
        deploy_service "ocx-authority" "authority" 8006
        ;;
    process-mining)
        deploy_service "ocx-process-mining" "process-mining" 8007
        ;;
    all)
        deploy_service "ocx-trust-registry"    "trust-registry"    8001
        deploy_service "ocx-jury"              "jury"              8002
        deploy_service "ocx-ledger"            "ledger"            8003
        deploy_service "ocx-activity-registry" "activity-registry" 8004
        deploy_service "ocx-evidence-vault"    "evidence-vault"    8005
        deploy_service "ocx-authority"         "authority"         8006
        deploy_service "ocx-process-mining"    "process-mining"    8007
        ;;
    *)
        echo -e "${RED}Unknown service: $SERVICE${NC}"
        echo ""
        echo "Usage: ./deploy.sh [service] [env] [region]"
        echo ""
        echo "Services:"
        echo "  trust-registry     Port 8001"
        echo "  jury               Port 8002"
        echo "  ledger             Port 8003"
        echo "  activity-registry  Port 8004"
        echo "  evidence-vault     Port 8005"
        echo "  authority          Port 8006"
        echo "  process-mining     Port 8007"
        echo "  all                All 7 services"
        echo ""
        echo "Envs: dev (default) | test | prod"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh all dev          # Deploy all services to dev"
        echo "  ./deploy.sh jury test        # Deploy jury to test"
        echo "  ./deploy.sh authority prod   # Deploy authority to prod"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete! [$DEPLOY_ENV]${NC}"
echo -e "${GREEN}========================================${NC}"
