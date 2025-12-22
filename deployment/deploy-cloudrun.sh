#!/bin/bash
set -e

# =============================================================================
# RAG Lab - Cloud Run Deployment Script
# =============================================================================
# This script deploys the RAG Lab application to Google Cloud Run
# Prerequisites: Run setup-infrastructure.sh first
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

# Load deployment config (GCP project, region, resource names, Cloud Run settings)
set -a
source .env.deploy
set +a

print_info "Checking application configuration file..."

if [ ! -f "../.env" ]; then
    print_error ".env file not found. Create it manually with all app config and secrets!"
    exit 1
fi

# Validate required variables from .env.deploy
if [ -z "$GCP_PROJECT_ID" ] || [ -z "$GCS_BUCKET" ] || [ -z "$CLOUD_RUN_SERVICE" ]; then
    print_error "Missing required variables in .env.deploy"
    exit 1
fi

print_info "Configuration loaded successfully"
echo "  Project: $GCP_PROJECT_ID"
echo "  Region: $GCP_REGION"
echo "  Bucket: $GCS_BUCKET"
echo "  Service: $CLOUD_RUN_SERVICE"
echo ""

# =============================================================================
# Configuration
# =============================================================================

# Cloud Run settings from .env.deploy
SERVICE_NAME="${CLOUD_RUN_SERVICE:-raglab}"
REGION="${GCP_REGION:-us-central1}"
MEMORY="${CLOUD_RUN_MEMORY:-1Gi}"
CPU="${CLOUD_RUN_CPU:-1}"
MAX_INSTANCES="${CLOUD_RUN_MAX_INSTANCES:-10}"
MIN_INSTANCES="${CLOUD_RUN_MIN_INSTANCES:-0}"
TIMEOUT="${CLOUD_RUN_TIMEOUT:-300}"
CONCURRENCY="${CLOUD_RUN_CONCURRENCY:-80}"
SECRET_NAME="${SECRET_NAME:-raglab-config}"

# =============================================================================
# Upload Configuration to Secret Manager
# =============================================================================

print_info "Checking Secret Manager API..."

# Check if Secret Manager API is enabled
if ! gcloud services list --enabled --project="$GCP_PROJECT_ID" --filter="name:secretmanager.googleapis.com" --format="value(name)" | grep -q "secretmanager.googleapis.com"; then
    print_error "Secret Manager API is not enabled!"
    print_error "Run: gcloud services enable secretmanager.googleapis.com --project=$GCP_PROJECT_ID"
    print_error "Or add it to setup-infrastructure.sh and re-run setup"
    exit 1
fi

print_info "Uploading .env to Secret Manager as '$SECRET_NAME'..."

# Check if secret exists
if gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    print_info "Secret exists, creating new version..."
    gcloud secrets versions add "$SECRET_NAME" \
        --data-file="../.env" \
        --project="$GCP_PROJECT_ID"
else
    print_info "Creating new secret..."
    gcloud secrets create "$SECRET_NAME" \
        --data-file="../.env" \
        --replication-policy="automatic" \
        --project="$GCP_PROJECT_ID"
fi

# Grant service account access to the secret
print_info "Granting service account access to secret..."
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$GCP_PROJECT_ID"

print_info "Configuration uploaded to Secret Manager"

# =============================================================================
# Build and Deploy
# =============================================================================

print_info "Setting project..."
gcloud config set project "$GCP_PROJECT_ID"

print_info "Building container with Cloud Build..."
print_warn "This may take 3-5 minutes..."

# Go to project root
cd ..

# Build container image
gcloud builds submit \
    --tag "gcr.io/${GCP_PROJECT_ID}/${SERVICE_NAME}:latest" \
    --timeout=1200s  # 20 minutes for large image with torch/CUDA

print_info "Container built successfully"

# =============================================================================
# Deploy to Cloud Run
# =============================================================================

print_info "Deploying to Cloud Run..."
print_info "Configuration will be mounted from Secret Manager as /app/.env"

# Deploy with Secret Manager volume mount
gcloud run deploy "$SERVICE_NAME" \
    --image "gcr.io/${GCP_PROJECT_ID}/${SERVICE_NAME}:latest" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory "$MEMORY" \
    --cpu "$CPU" \
    --timeout "$TIMEOUT" \
    --concurrency "$CONCURRENCY" \
    --max-instances "$MAX_INSTANCES" \
    --min-instances "$MIN_INSTANCES" \
    --service-account "${SERVICE_ACCOUNT_EMAIL}" \
    --add-cloudsql-instances "${CLOUD_SQL_CONNECTION_NAME}" \
    --add-volume name=config,type=secret,secret-name="$SECRET_NAME" \
    --add-volume-mount volume=config,mount-path=/app/.env \
    --quiet

print_info "Deployment completed successfully!"

# =============================================================================
# Get Service URL
# =============================================================================

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --format="value(status.url)")

print_info "=========================================="
print_info "Deployment Summary"
print_info "=========================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
print_info "Test endpoints:"
echo "  Health: curl $SERVICE_URL/health"
echo "  Upload: curl -X POST $SERVICE_URL/v1/documents/upload -F file=@document.pdf"
echo "  Query: curl -X POST $SERVICE_URL/v1/query -H 'Content-Type: application/json' -d '{\"query\":\"test\",\"top_k\":3}'"
echo ""
print_info "View logs:"
echo "  gcloud run services logs read $SERVICE_NAME --region $REGION"
echo ""

# =============================================================================
# Test Deployment
# =============================================================================

print_info "Testing deployment..."

# Test health endpoint
if curl -s "$SERVICE_URL/health" | grep -q "healthy"; then
    print_info "Health check passed!"
else
    print_warn "Health check failed. Check logs:"
    echo "  gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50"
fi
