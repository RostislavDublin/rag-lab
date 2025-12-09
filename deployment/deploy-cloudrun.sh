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

print_info "Loading configuration from .env..."

if [ ! -f "../.env" ]; then
    print_error ".env file not found. Run setup-infrastructure.sh first!"
    exit 1
fi

# Load environment variables
set -a
source ../.env
set +a

# Validate required variables
if [ -z "$GCP_PROJECT_ID" ] || [ -z "$GCS_BUCKET" ] || [ -z "$DATABASE_URL" ]; then
    print_error "Missing required environment variables in .env"
    exit 1
fi

print_info "Configuration loaded successfully"
echo "  Project: $GCP_PROJECT_ID"
echo "  Region: $GCP_REGION"
echo "  Bucket: $GCS_BUCKET"
echo ""

# =============================================================================
# Configuration
# =============================================================================

SERVICE_NAME="raglab"
REGION="${GCP_REGION:-us-central1}"
MEMORY="1Gi"
CPU="1"
MAX_INSTANCES="10"
MIN_INSTANCES="0"
TIMEOUT="300"
CONCURRENCY="80"

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
    --timeout=600s

print_info "Container built successfully"

# =============================================================================
# Deploy to Cloud Run
# =============================================================================

print_info "Deploying to Cloud Run..."

# Deploy
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
    --set-env-vars "GCP_PROJECT_ID=${GCP_PROJECT_ID}" \
    --set-env-vars "GCP_LOCATION=${GCP_REGION}" \
    --set-env-vars "GCS_BUCKET=${GCS_BUCKET}" \
    --set-env-vars "DATABASE_URL=${DATABASE_URL}" \
    --service-account "${SERVICE_ACCOUNT_EMAIL}" \
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
