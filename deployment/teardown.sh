#!/bin/bash
set -e

# =============================================================================
# RAG Lab - Complete Infrastructure Teardown
# =============================================================================
# This script deletes ALL resources created by setup-infrastructure.sh
# WARNING: This is DESTRUCTIVE and cannot be undone!
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

if [ ! -f "../.env" ]; then
    print_error ".env file not found"
    exit 1
fi

# Load environment variables
set -a
source ../.env
set +a

print_warn "=========================================="
print_warn "WARNING: DESTRUCTIVE OPERATION"
print_warn "=========================================="
echo ""
echo "This will DELETE the following resources:"
echo "  - Cloud Run service: raglab"
echo "  - Cloud Storage bucket: $GCS_BUCKET (and all files)"
echo "  - Cloud SQL instance: raglab-db (and all data)"
echo "  - Service Account: $SERVICE_ACCOUNT_EMAIL"
echo ""
echo "Project: $GCP_PROJECT_ID"
echo "Region: $GCP_REGION"
echo ""
print_error "THIS CANNOT BE UNDONE!"
echo ""
echo -n "Type 'DELETE-ALL' to confirm: "
read CONFIRM

if [ "$CONFIRM" != "DELETE-ALL" ]; then
    print_info "Aborted by user"
    exit 0
fi

print_warn "Starting teardown..."

# =============================================================================
# Delete Cloud Run Service
# =============================================================================

print_info "Deleting Cloud Run service..."

if gcloud run services describe raglab --region="$GCP_REGION" &>/dev/null; then
    gcloud run services delete raglab \
        --region="$GCP_REGION" \
        --quiet
    print_info "Cloud Run service deleted"
else
    print_warn "Cloud Run service not found"
fi

# =============================================================================
# Delete Cloud Storage Bucket
# =============================================================================

print_info "Deleting Cloud Storage bucket and all files..."

if gcloud storage buckets describe "gs://$GCS_BUCKET" &>/dev/null; then
    gcloud storage rm -r "gs://$GCS_BUCKET" --quiet
    print_info "Cloud Storage bucket deleted"
else
    print_warn "Cloud Storage bucket not found"
fi

# =============================================================================
# Delete Cloud SQL Instance
# =============================================================================

print_info "Deleting Cloud SQL instance..."
print_warn "This may take 3-5 minutes..."

if gcloud sql instances describe raglab-db &>/dev/null; then
    gcloud sql instances delete raglab-db --quiet
    print_info "Cloud SQL instance deleted"
else
    print_warn "Cloud SQL instance not found"
fi

# =============================================================================
# Delete Service Account
# =============================================================================

print_info "Deleting service account..."

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &>/dev/null; then
    gcloud iam service-accounts delete "$SERVICE_ACCOUNT_EMAIL" --quiet
    print_info "Service account deleted"
else
    print_warn "Service account not found"
fi

# =============================================================================
# Clean up local files
# =============================================================================

print_info "Cleaning up local configuration files..."

rm -f ../.env
rm -f deployment/credentials.txt
rm -f deployment/deployment-info.txt

print_info "Local files cleaned up"

# =============================================================================
# Summary
# =============================================================================

print_info "=========================================="
print_info "Teardown completed successfully"
print_info "=========================================="
echo ""
print_info "All resources have been deleted:"
echo "  - Cloud Run service"
echo "  - Cloud Storage bucket"
echo "  - Cloud SQL instance"
echo "  - Service Account"
echo "  - Local configuration files"
echo ""
print_info "To recreate infrastructure, run:"
echo "  cd deployment && ./setup-infrastructure.sh"
