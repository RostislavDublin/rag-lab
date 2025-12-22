#!/bin/bash
set -e

# =============================================================================
# RAG Lab Infrastructure Setup Script
# =============================================================================
# This script creates all required GCP resources:
# - Enables necessary APIs
# - Creates Cloud Storage bucket
# - Creates Cloud SQL PostgreSQL instance
# - Creates Service Account with proper permissions
# - Configures networking if needed
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# =============================================================================
# Prerequisites Check
# =============================================================================

print_info "Checking prerequisites..."

if ! command_exists gcloud; then
    print_error "gcloud CLI not found. Please install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# =============================================================================
# Configuration
# =============================================================================

print_info "Reading configuration..."

# Read from environment or prompt user
if [ -z "$GCP_PROJECT_ID" ]; then
    echo -n "Enter GCP Project ID: "
    read GCP_PROJECT_ID
fi

if [ -z "$GCP_REGION" ]; then
    echo -n "Enter GCP Region (default: us-central1): "
    read GCP_REGION
    GCP_REGION=${GCP_REGION:-us-central1}
fi

# Configuration variables
PROJECT_ID="$GCP_PROJECT_ID"
REGION="$GCP_REGION"
BUCKET_NAME="raglab-documents-${PROJECT_ID}"
DB_INSTANCE_NAME="raglab-db"
DB_NAME="raglab"
DB_USER="raglab"
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
SERVICE_ACCOUNT_NAME="raglab-sa"

print_info "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Bucket: $BUCKET_NAME"
echo "  DB Instance: $DB_INSTANCE_NAME"
echo "  Service Account: $SERVICE_ACCOUNT_NAME@${PROJECT_ID}.iam.gserviceaccount.com"
echo ""

# Confirm
echo -n "Proceed with infrastructure setup? (yes/no): "
read CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_info "Aborted by user"
    exit 0
fi

# =============================================================================
# Set active project
# =============================================================================

print_info "Setting active project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID"

# =============================================================================
# Enable Required APIs
# =============================================================================

print_info "Enabling required GCP APIs (this may take 2-3 minutes)..."

APIS=(
    "run.googleapis.com"
    "cloudbuild.googleapis.com"
    "sqladmin.googleapis.com"
    "aiplatform.googleapis.com"
    "storage.googleapis.com"
    "compute.googleapis.com"
    "servicenetworking.googleapis.com"
    "secretmanager.googleapis.com"
)

for api in "${APIS[@]}"; do
    print_info "Enabling $api..."
    gcloud services enable "$api" --quiet
done

print_info "All APIs enabled successfully"

# =============================================================================
# Create Cloud Storage Bucket
# =============================================================================

print_info "Creating Cloud Storage bucket: $BUCKET_NAME..."

if gcloud storage buckets describe "gs://$BUCKET_NAME" &>/dev/null; then
    print_warn "Bucket already exists: $BUCKET_NAME"
else
    gcloud storage buckets create "gs://$BUCKET_NAME" \
        --location="$REGION" \
        --uniform-bucket-level-access \
        --public-access-prevention
    
    print_info "Bucket created successfully"
fi

# =============================================================================
# Create Service Account
# =============================================================================

print_info "Creating service account: $SERVICE_ACCOUNT_NAME..."

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &>/dev/null; then
    print_warn "Service account already exists: $SERVICE_ACCOUNT_EMAIL"
else
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="RAG Lab Service Account" \
        --description="Service account for RAG Lab application"
    
    print_info "Service account created successfully"
fi

# Grant necessary permissions
print_info "Granting permissions to service account..."

ROLES=(
    "roles/aiplatform.user"
    "roles/cloudsql.client"
)

for role in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$role" \
        --quiet
done

# Grant storage permissions
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/storage.objectAdmin" \
    --quiet

print_info "Permissions granted successfully"

# =============================================================================
# Create Cloud SQL Instance
# =============================================================================

print_info "Creating Cloud SQL PostgreSQL instance: $DB_INSTANCE_NAME..."
print_warn "This may take 5-10 minutes..."

if gcloud sql instances describe "$DB_INSTANCE_NAME" &>/dev/null; then
    print_warn "Cloud SQL instance already exists: $DB_INSTANCE_NAME"
else
    gcloud sql instances create "$DB_INSTANCE_NAME" \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region="$REGION" \
        --network=default \
        --no-assign-ip \
        --quiet
    
    print_info "Cloud SQL instance created successfully"
fi

# Wait for instance to be ready
print_info "Waiting for Cloud SQL instance to be ready..."
gcloud sql operations list --instance="$DB_INSTANCE_NAME" --limit=1 --format="value(status)" | grep -q "DONE"

# Get private IP
DB_PRIVATE_IP=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format="value(ipAddresses[0].ipAddress)")
print_info "Cloud SQL Private IP: $DB_PRIVATE_IP"

# =============================================================================
# Create Database and User
# =============================================================================

print_info "Creating database: $DB_NAME..."

# Create database
gcloud sql databases create "$DB_NAME" \
    --instance="$DB_INSTANCE_NAME" \
    --quiet || print_warn "Database may already exist"

# Create user
print_info "Creating database user: $DB_USER..."
gcloud sql users create "$DB_USER" \
    --instance="$DB_INSTANCE_NAME" \
    --password="$DB_PASSWORD" \
    --quiet || print_warn "User may already exist"

# Enable pgvector extension (requires psql)
print_info "Checking if pgvector extension can be enabled..."
if command_exists psql; then
    CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format="value(connectionName)")
    print_info "To enable pgvector, run: gcloud sql connect $DB_INSTANCE_NAME --user=postgres"
    print_info "Then execute: CREATE EXTENSION IF NOT EXISTS vector;"
else
    print_warn "psql not found. You'll need to enable pgvector extension manually after first deployment"
fi

# =============================================================================
# Create .env file
# =============================================================================

print_info "Creating .env file with configuration..."

cat > .env << EOF
# GCP Configuration
GCP_PROJECT_ID="$PROJECT_ID"
GCP_REGION="$REGION"
GCP_LOCATION="$REGION"

# Cloud Storage
GCS_BUCKET="$BUCKET_NAME"

# Cloud SQL PostgreSQL
DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_PRIVATE_IP:5432/$DB_NAME"

# Service Account
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_EMAIL"

# Cloud SQL Connection Name (for Cloud Run)
CLOUD_SQL_CONNECTION_NAME="$(gcloud sql instances describe $DB_INSTANCE_NAME --format='value(connectionName)')"

# Optional: Port for local development
PORT="8080"
EOF

print_info ".env file created successfully"

# Also create .env.template (without sensitive data)
cat > .env.template << EOF
# GCP Configuration
GCP_PROJECT_ID="your-project-id"
GCP_REGION="us-central1"
GCP_LOCATION="us-central1"

# Cloud Storage
GCS_BUCKET="your-bucket-name"

# Cloud SQL PostgreSQL
DATABASE_URL="postgresql://user:password@host:5432/dbname"

# Service Account
SERVICE_ACCOUNT_EMAIL="your-sa@your-project.iam.gserviceaccount.com"

# Cloud SQL Connection Name (for Cloud Run)
CLOUD_SQL_CONNECTION_NAME="project:region:instance"

# Optional: Port for local development
PORT="8080"
EOF

# =============================================================================
# Save credentials securely
# =============================================================================

print_info "Saving credentials to deployment/credentials.txt..."

mkdir -p deployment
cat > deployment/credentials.txt << EOF
=============================================================================
RAG Lab Infrastructure Credentials
=============================================================================
Created: $(date)

GCP Project ID: $PROJECT_ID
Region: $REGION

Cloud Storage Bucket: $BUCKET_NAME

Cloud SQL Instance: $DB_INSTANCE_NAME
Database Name: $DB_NAME
Database User: $DB_USER
Database Password: $DB_PASSWORD
Private IP: $DB_PRIVATE_IP

Service Account: $SERVICE_ACCOUNT_EMAIL

Connection String:
postgresql://$DB_USER:$DB_PASSWORD@$DB_PRIVATE_IP:5432/$DB_NAME

IMPORTANT: Keep this file secure and do not commit to git!
=============================================================================
EOF

chmod 600 deployment/credentials.txt

# =============================================================================
# Update .gitignore
# =============================================================================

print_info "Updating .gitignore..."

if ! grep -q "credentials.txt" .gitignore 2>/dev/null; then
    cat >> .gitignore << EOF

# Credentials (added by setup script)
deployment/credentials.txt
.env
service-account-key.json
EOF
fi

# =============================================================================
# Summary
# =============================================================================

print_info "=========================================="
print_info "Infrastructure setup completed successfully!"
print_info "=========================================="
echo ""
print_info "Next steps:"
echo "1. Review credentials in: deployment/credentials.txt"
echo "2. Review environment variables in: .env"
echo "3. Deploy application: ./deployment/deploy-cloudrun.sh"
echo ""
print_warn "IMPORTANT:"
echo "- Database password saved in: deployment/credentials.txt"
echo "- Keep credentials.txt secure (not committed to git)"
echo "- .env file created for local development"
echo ""
print_info "Database connection string:"
echo "postgresql://$DB_USER:$DB_PASSWORD@$DB_PRIVATE_IP:5432/$DB_NAME"
echo ""
print_info "To test locally:"
echo "docker-compose up"
echo ""
print_info "To deploy to Cloud Run:"
echo "cd deployment && ./deploy-cloudrun.sh"
