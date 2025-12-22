#!/bin/bash
set -e

# =============================================================================
# Upload Secrets to Secret Manager
# =============================================================================
# This script uploads the .env file to GCP Secret Manager
# Run this manually BEFORE deploying (or when secrets change)
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Load Configuration
# =============================================================================

print_info "Loading deployment configuration from .env.deploy..."

if [ ! -f ".env.deploy" ]; then
    print_error ".env.deploy file not found!"
    exit 1
fi

source .env.deploy

print_info "Checking .env file..."

if [ ! -f "../.env" ]; then
    print_error ".env file not found in project root!"
    print_error "Create .env with all application config and secrets"
    exit 1
fi

# Validate required variables
if [ -z "$GCP_PROJECT_ID" ]; then
    print_error "GCP_PROJECT_ID not set in .env.deploy"
    exit 1
fi

SECRET_NAME="${SECRET_NAME:-raglab-config}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-rag-service@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"

print_info "Configuration:"
echo "  Project: $GCP_PROJECT_ID"
echo "  Secret: $SECRET_NAME"
echo "  Service Account: $SERVICE_ACCOUNT_EMAIL"
echo ""

# =============================================================================
# Check Secret Manager API
# =============================================================================

print_info "Checking Secret Manager API..."

if ! gcloud services list --enabled --project="$GCP_PROJECT_ID" --filter="name:secretmanager.googleapis.com" --format="value(name)" | grep -q "secretmanager.googleapis.com"; then
    print_error "Secret Manager API is not enabled!"
    print_error "Run: gcloud services enable secretmanager.googleapis.com --project=$GCP_PROJECT_ID"
    print_error "Or add it to setup-infrastructure.sh and re-run setup"
    exit 1
fi

# =============================================================================
# Upload Secret
# =============================================================================

print_info "Uploading .env to Secret Manager as '$SECRET_NAME'..."

gcloud config set project "$GCP_PROJECT_ID"

# Check if secret exists
if gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    print_info "Secret exists, creating new version..."
    gcloud secrets versions add "$SECRET_NAME" \
        --data-file="../.env" \
        --project="$GCP_PROJECT_ID"
    
    VERSION=$(gcloud secrets versions list "$SECRET_NAME" --project="$GCP_PROJECT_ID" --limit=1 --format="value(name)")
    print_info "Created version: $VERSION"
else
    print_info "Creating new secret..."
    gcloud secrets create "$SECRET_NAME" \
        --data-file="../.env" \
        --replication-policy="automatic" \
        --project="$GCP_PROJECT_ID"
    
    print_info "Secret created: $SECRET_NAME"
fi

# =============================================================================
# Grant Access to Service Account
# =============================================================================

print_info "Granting service account access to secret..."

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$GCP_PROJECT_ID"

print_info "✓ Service account can read secret"

# =============================================================================
# Summary
# =============================================================================

print_info "=========================================="
print_info "Secrets Upload Complete"
print_info "=========================================="
echo ""
echo "Secret: $SECRET_NAME"
echo "Project: $GCP_PROJECT_ID"
echo ""
print_info "Next steps:"
echo "  1. Push to deploy branch: git push origin deploy/production"
echo "  2. Monitor Cloud Build: https://console.cloud.google.com/cloud-build/builds?project=$GCP_PROJECT_ID"
echo "  3. Check Cloud Run logs after deployment"
echo ""
print_warn "To update secrets: Re-run this script after editing .env"
echo ""
