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

print_info "Reading configuration from .env.deploy..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.deploy"

if [ ! -f "$ENV_FILE" ]; then
    print_error ".env.deploy not found in $SCRIPT_DIR"
    print_error "Create it from .env.deploy.example and configure your settings"
    exit 1
fi

# Load configuration
source "$ENV_FILE"

# Validate required variables from .env.deploy
REQUIRED_VARS=(
    "GCP_PROJECT_ID"
    "GCP_REGION"
    "GCS_BUCKET"
    "DB_INSTANCE_NAME"
    "DB_NAME"
    "DB_USER"
    "SERVICE_ACCOUNT_NAME"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        print_error "$var not set in .env.deploy"
        print_error "Check .env.deploy.example for required variables"
        exit 1
    fi
done

# Validate DB_PASSWORD is set
if [ -z "$DB_PASSWORD" ]; then
    print_error "DB_PASSWORD not set in .env.deploy"
    print_error "Add to .env.deploy: DB_PASSWORD=\"your-password\""
    exit 1
fi

# Configuration variables (from .env.deploy)
PROJECT_ID="$GCP_PROJECT_ID"
REGION="$GCP_REGION"
BUCKET_NAME="$GCS_BUCKET"
# DB settings already loaded from .env.deploy

print_info "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Bucket: $BUCKET_NAME"
echo "  DB Instance: $DB_INSTANCE_NAME"
echo "  DB Name: $DB_NAME"
echo "  DB User: $DB_USER"
echo "  Service Account: $SERVICE_ACCOUNT_NAME@${PROJECT_ID}.iam.gserviceaccount.com"
echo ""

print_info "All configuration loaded from .env.deploy"
echo ""

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
    "artifactregistry.googleapis.com"
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
# Create Artifact Registry Repository
# =============================================================================

print_info "Creating Artifact Registry repository for Docker images..."

AR_REPO_NAME="raglab"

if gcloud artifacts repositories describe "$AR_REPO_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Artifact Registry repository already exists: $AR_REPO_NAME"
else
    if gcloud artifacts repositories create "$AR_REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --description="Docker images for RAG Lab CI/CD pipeline" \
        --quiet; then
        print_info "Artifact Registry repository created: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"
    else
        print_error "Failed to create Artifact Registry repository"
        exit 1
    fi
fi

# =============================================================================
# Create Cloud Storage Bucket
# =============================================================================

print_info "Creating Cloud Storage bucket: $BUCKET_NAME..."

if gcloud storage buckets describe "gs://$BUCKET_NAME" --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Bucket already exists: $BUCKET_NAME"
else
    if gcloud storage buckets create "gs://$BUCKET_NAME" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --uniform-bucket-level-access \
        --public-access-prevention; then
        print_info "Bucket created successfully: gs://$BUCKET_NAME"
    else
        print_error "Failed to create storage bucket"
        exit 1
    fi
fi

# =============================================================================
# Create Service Account
# =============================================================================

print_info "Creating service account: $SERVICE_ACCOUNT_NAME..."

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Service account already exists: $SERVICE_ACCOUNT_EMAIL"
else
    if gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --project="$PROJECT_ID" \
        --display-name="RAG Lab Service Account" \
        --description="Service account for RAG Lab application"; then
        print_info "Service account created successfully: $SERVICE_ACCOUNT_EMAIL"
    else
        print_error "Failed to create service account"
        exit 1
    fi
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
        --condition=None \
        --quiet > /dev/null 2>&1
done

# Grant storage permissions
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/storage.objectAdmin" \
    --quiet > /dev/null 2>&1

print_info "Permissions granted successfully"

# =============================================================================
# Create Cloud SQL Instance
# =============================================================================

print_info "Creating Cloud SQL PostgreSQL instance: $DB_INSTANCE_NAME..."

if gcloud sql instances describe "$DB_INSTANCE_NAME" --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Cloud SQL instance already exists: $DB_INSTANCE_NAME"
else
    print_warn "This may take 5-10 minutes..."
    
    if gcloud sql instances create "$DB_INSTANCE_NAME" \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region="$REGION" \
        --network=default \
        --no-assign-ip \
        --project="$PROJECT_ID" \
        --quiet; then
        
        print_info "Cloud SQL instance created successfully"
        
        # Wait for instance to be ready
        print_info "Waiting for Cloud SQL instance to be ready..."
        gcloud sql operations list --instance="$DB_INSTANCE_NAME" --project="$PROJECT_ID" --limit=1 --format="value(status)" | grep -q "DONE"
    else
        print_error "Failed to create Cloud SQL instance"
        print_error "Common causes:"
        print_error "  1. Service Networking not configured (run: gcloud services vpc-peerings connect)"
        print_error "  2. VPC network 'default' doesn't exist"
        print_error "  3. Insufficient permissions"
        print_error ""
        print_error "If instance already exists but command failed, check manually:"
        print_error "  gcloud sql instances describe $DB_INSTANCE_NAME --project=$PROJECT_ID"
        exit 1
    fi
fi

# Get private IP for both new and existing instances
DB_PRIVATE_IP=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)")
if [ -z "$DB_PRIVATE_IP" ]; then
    print_error "Failed to get Cloud SQL private IP"
    exit 1
fi
print_info "Cloud SQL Private IP: $DB_PRIVATE_IP"

# =============================================================================
# Create Database and User
# =============================================================================

print_info "Creating database: $DB_NAME..."

# Check if database exists
if gcloud sql databases describe "$DB_NAME" \
    --instance="$DB_INSTANCE_NAME" \
    --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Database already exists: $DB_NAME"
else
    if gcloud sql databases create "$DB_NAME" \
        --instance="$DB_INSTANCE_NAME" \
        --project="$PROJECT_ID" \
        --quiet; then
        print_info "Database created: $DB_NAME"
    else
        print_error "Failed to create database"
        exit 1
    fi
fi

# Create user
print_info "Creating database user: $DB_USER..."

# Check if user exists
if gcloud sql users list \
    --instance="$DB_INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --format="value(name)" | grep -q "^${DB_USER}$"; then
    print_warn "Database user already exists: $DB_USER"
else
    if gcloud sql users create "$DB_USER" \
        --instance="$DB_INSTANCE_NAME" \
        --project="$PROJECT_ID" \
        --password="$DB_PASSWORD" \
        --quiet; then
        print_info "Database user created: $DB_USER"
    else
        print_error "Failed to create database user"
        exit 1
    fi
fi

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
# Create Secret Manager Secret
# =============================================================================

print_info "Creating Secret Manager secret: raglab-config..."

# Get Cloud SQL Connection Name
CLOUD_SQL_CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --project="$PROJECT_ID" --format='value(connectionName)')

# Build .env content for Cloud Run
SECRET_CONTENT="# GCP Configuration
GCP_PROJECT_ID=\"$PROJECT_ID\"
GCP_REGION=\"$REGION\"
GCP_LOCATION=\"$REGION\"

# Cloud Storage
GCS_BUCKET=\"$BUCKET_NAME\"

# Cloud SQL PostgreSQL (Unix socket for Cloud Run)
DATABASE_URL=\"postgresql://$DB_USER:$DB_PASSWORD@/$DB_NAME?host=/cloudsql/$CLOUD_SQL_CONNECTION_NAME\"

# Cloud SQL Connection Name
CLOUD_SQL_CONNECTION_NAME=\"$CLOUD_SQL_CONNECTION_NAME\"

# Service Account
SERVICE_ACCOUNT_EMAIL=\"$SERVICE_ACCOUNT_EMAIL\"

# Port
PORT=\"8080\"
"

# Check if secret exists
if gcloud secrets describe "raglab-config" --project="$PROJECT_ID" &>/dev/null; then
    print_warn "Secret 'raglab-config' already exists, updating with new version..."
    echo "$SECRET_CONTENT" | gcloud secrets versions add "raglab-config" \
        --project="$PROJECT_ID" \
        --data-file=- \
        --quiet
    print_info "Secret updated successfully"
else
    print_info "Creating new secret 'raglab-config'..."
    echo "$SECRET_CONTENT" | gcloud secrets create "raglab-config" \
        --project="$PROJECT_ID" \
        --replication-policy="automatic" \
        --data-file=- \
        --quiet
    print_info "Secret created successfully"
fi

# Grant Cloud Build SA access to secret (for verification step in cloudbuild.yaml)
print_info "Granting Cloud Build service account access to secret..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud secrets add-iam-policy-binding "raglab-config" \
    --member="serviceAccount:$CLOUDBUILD_SA" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet > /dev/null 2>&1

# Grant runtime service account access to secret
gcloud secrets add-iam-policy-binding "raglab-config" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet > /dev/null 2>&1

print_info "Secret permissions configured"

# =============================================================================
# Summary
# =============================================================================

print_info "=========================================="
print_info "Infrastructure Summary"
print_info "=========================================="
echo ""
print_info "Artifact Registry:"
echo "  URL: ${REGION}-docker.pkg.dev/${PROJECT_ID}/raglab"
echo ""
print_info "Cloud Storage:"
echo "  Bucket URL: gs://$BUCKET_NAME"
echo ""
print_info "Cloud SQL:"
echo "  Connection Name: $CLOUD_SQL_CONNECTION_NAME"
echo "  Private IP: $DB_PRIVATE_IP"
echo ""
print_info "Secret Manager:"
echo "  Secret: raglab-config"
echo "  Latest version: $(gcloud secrets versions list raglab-config --limit=1 --format='value(name)' 2>/dev/null || echo 'N/A')"
echo ""
print_info "Service Account:"
echo "  Email: $SERVICE_ACCOUNT_EMAIL"
echo ""
print_info "Next Steps:"
echo "1. Verify secret content: gcloud secrets versions access latest --secret=raglab-config"
echo "2. Deploy: cd deployment && ./deploy-cloudrun.sh"
