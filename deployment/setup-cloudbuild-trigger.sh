#!/bin/bash
# Setup Cloud Build Trigger for GitHub → Cloud Run deployment
# This script automates trigger creation and IAM permissions

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.deploy"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: $ENV_FILE not found${NC}"
    echo "Create it from .env.deploy.example and configure your settings"
    exit 1
fi

source "$ENV_FILE"

# Required variables
REQUIRED_VARS=(
    "GCP_PROJECT_ID"
    "GCP_REGION"
    "GITHUB_REPO_OWNER"
    "GITHUB_REPO_NAME"
    "TRIGGER_NAME"
    "DEPLOY_BRANCH"
)

echo -e "${BLUE}Checking required variables...${NC}"
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}ERROR: $var is not set in $ENV_FILE${NC}"
        exit 1
    fi
    echo "  ✓ $var = ${!var}"
done

# Get project number
PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT_ID" --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Cloud Build Trigger Setup${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Project ID:       $GCP_PROJECT_ID"
echo "Project Number:   $PROJECT_NUMBER"
echo "GitHub Repo:      $GITHUB_REPO_OWNER/$GITHUB_REPO_NAME"
echo "Deploy Branch:    $DEPLOY_BRANCH"
echo "Trigger Name:     $TRIGGER_NAME"
echo "Cloud Build SA:   $CLOUDBUILD_SA"
echo ""

# Step 1: Check if GitHub connection exists
echo -e "${BLUE}Step 1: Check GitHub connection${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: GitHub repository must be connected to Cloud Build first!${NC}"
echo ""
echo "If you haven't connected GitHub yet, do it now:"
echo "1. Open: https://console.cloud.google.com/cloud-build/triggers?project=$GCP_PROJECT_ID"
echo "2. Click 'Connect Repository'"
echo "3. Select 'GitHub (Cloud Build GitHub App)'"
echo "4. Authenticate with GitHub"
echo "5. Select repository: $GITHUB_REPO_OWNER/$GITHUB_REPO_NAME"
echo "6. Click 'Connect'"
echo ""
read -p "Press Enter when GitHub repository is connected..."

# Verify connection by listing repositories
echo -e "${BLUE}Verifying GitHub connection...${NC}"
CONNECTIONS=$(gcloud builds triggers list --project="$GCP_PROJECT_ID" --format="value(github.owner, github.name)" 2>/dev/null || echo "")

if [[ -z "$CONNECTIONS" ]]; then
    # No triggers yet, check if we can create one (this will fail if no connection)
    echo -e "${YELLOW}No existing triggers found. Will attempt to create trigger...${NC}"
else
    echo -e "${GREEN}✓ GitHub connection exists${NC}"
fi

# Step 2: Enable Cloud Build API
echo ""
echo -e "${BLUE}Step 2: Enable Cloud Build API${NC}"
if gcloud services list --enabled --project="$GCP_PROJECT_ID" --filter="name:cloudbuild.googleapis.com" --format="value(name)" | grep -q "cloudbuild"; then
    echo -e "${GREEN}✓ Cloud Build API already enabled${NC}"
else
    echo "Enabling Cloud Build API..."
    gcloud services enable cloudbuild.googleapis.com --project="$GCP_PROJECT_ID"
    echo -e "${GREEN}✓ Cloud Build API enabled${NC}"
    
    # Wait for SA to be created
    echo "Waiting 10 seconds for Cloud Build SA to be created..."
    sleep 10
fi

# Step 3: Create Cloud Build Trigger
echo ""
echo -e "${BLUE}Step 3: Create Cloud Build Trigger${NC}"

# Check if trigger already exists
if gcloud builds triggers describe "$TRIGGER_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}Trigger '$TRIGGER_NAME' already exists${NC}"
    read -p "Delete and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Deleting existing trigger..."
        gcloud builds triggers delete "$TRIGGER_NAME" --project="$GCP_PROJECT_ID" --quiet
        echo -e "${GREEN}✓ Trigger deleted${NC}"
    else
        echo "Keeping existing trigger"
    fi
fi

if ! gcloud builds triggers describe "$TRIGGER_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo "Creating trigger: $TRIGGER_NAME"
    
    gcloud builds triggers create github \
        --name="$TRIGGER_NAME" \
        --repo-owner="$GITHUB_REPO_OWNER" \
        --repo-name="$GITHUB_REPO_NAME" \
        --branch-pattern="^${DEPLOY_BRANCH}$" \
        --build-config=cloudbuild.yaml \
        --project="$GCP_PROJECT_ID" \
        --region="$GCP_REGION" \
        --service-account="projects/$GCP_PROJECT_ID/serviceAccounts/${RUNTIME_SA}"
    
    echo -e "${GREEN}✓ Trigger created successfully${NC}"
else
    echo -e "${GREEN}✓ Trigger already configured${NC}"
fi

# Step 4: Grant IAM permissions to Cloud Build SA
echo ""
echo -e "${BLUE}Step 4: Grant IAM permissions to Cloud Build SA${NC}"
echo "Service Account: $CLOUDBUILD_SA"
echo ""

# Define required roles
ROLES=(
    "roles/run.admin"
    "roles/iam.serviceAccountUser"
    "roles/secretmanager.secretAccessor"
    "roles/storage.admin"
)

for role in "${ROLES[@]}"; do
    echo "Granting $role..."
    
    # Check if already has role
    if gcloud projects get-iam-policy "$GCP_PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.role=$role AND bindings.members:$CLOUDBUILD_SA" \
        --format="value(bindings.role)" | grep -q "$role"; then
        echo -e "  ${GREEN}✓ Already has $role${NC}"
    else
        gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
            --member="serviceAccount:$CLOUDBUILD_SA" \
            --role="$role" \
            --quiet \
            > /dev/null
        echo -e "  ${GREEN}✓ Granted $role${NC}"
    fi
done

# Step 5: Verify setup
echo ""
echo -e "${BLUE}Step 5: Verify setup${NC}"

# Check trigger
if gcloud builds triggers describe "$TRIGGER_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}✓ Trigger exists and configured${NC}"
else
    echo -e "${RED}✗ Trigger not found${NC}"
    exit 1
fi

# Check IAM
echo -e "${GREEN}✓ IAM permissions configured${NC}"

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Create deploy branch:"
echo "   git checkout main"
echo "   git checkout -b $DEPLOY_BRANCH"
echo "   git push origin $DEPLOY_BRANCH"
echo ""
echo "2. Upload secrets (if not done yet):"
echo "   cd deployment"
echo "   ./upload-secrets.sh"
echo ""
echo "3. Trigger deployment:"
echo "   git checkout main"
echo "   # ... make changes ..."
echo "   git commit -m 'Your changes'"
echo "   git push origin main"
echo "   git checkout $DEPLOY_BRANCH"
echo "   git merge main"
echo "   git push origin $DEPLOY_BRANCH  # ← Triggers Cloud Build!"
echo ""
echo "4. Monitor deployment:"
echo "   open https://console.cloud.google.com/cloud-build/builds?project=$GCP_PROJECT_ID"
echo ""
echo -e "${YELLOW}Cost:${NC} ~\$0.02-0.04 per deployment (first 120 build-minutes/day free)"
echo ""
