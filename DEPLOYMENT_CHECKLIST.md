# Deployment Checklist

Quick reference for deploying RAG Lab to Cloud Run with GitHub CI/CD.

## Prerequisites

- [ ] GCP project created
- [ ] gcloud CLI installed and authenticated
- [ ] GitHub repository created
- [ ] Local repository configured

## One-Time Setup (First Deployment)

### 1. Infrastructure Setup

```bash
cd deployment
cp .env.deploy.example .env.deploy
```

Edit `.env.deploy`:
```bash
GCP_PROJECT_ID="your-project-id"
GCP_REGION="us-central1"
GITHUB_REPO_OWNER="your-github-username"
GITHUB_REPO_NAME="rag-lab"
```

Run setup:
```bash
./setup-infrastructure.sh
```

Creates:
- ✅ Cloud SQL PostgreSQL with pgvector
- ✅ GCS bucket for documents
- ✅ Service Account (rag-service) with IAM roles
- ✅ Secret Manager API enabled

### 2. Cloud Build CI/CD Setup

```bash
./setup-cloudbuild-trigger.sh
```

**Manual step required:** Connect GitHub repository via browser (OAuth, 30 seconds)

Creates:
- ✅ Cloud Build trigger (deploy-production)
- ✅ GitHub webhook connection
- ✅ Cloud Build SA with IAM permissions

### 3. Application Configuration

```bash
cd ..
cp .env.example .env
```

Edit `.env` with production settings:
- Database connection (auto-configured)
- Embedding provider (vertex_ai recommended)
- Reranking provider (vertex_ai recommended)
- Authentication settings (JWT/JWKS)
- Logging level

Upload to Secret Manager:
```bash
cd deployment
./upload-secrets.sh
```

### 4. Create Deploy Branch

```bash
cd ..
git checkout -b deploy/production
git push origin deploy/production
```

### 5. Verify Setup

Check trigger exists:
```bash
gcloud builds triggers describe deploy-production \
  --region=us-central1 \
  --project=YOUR_PROJECT
```

Check Cloud Build SA permissions:
```bash
gcloud projects get-iam-policy YOUR_PROJECT \
  --flatten="bindings[].members" \
  --filter="bindings.members:*@cloudbuild.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Expected roles:
- ✅ roles/run.admin
- ✅ roles/iam.serviceAccountUser
- ✅ roles/secretmanager.secretAccessor
- ✅ roles/storage.admin

## Regular Deployment Workflow

### Deploy to Production

```bash
# 1. Work on main branch
git checkout main
# ... make changes ...
git add .
git commit -m "Your changes"
git push origin main

# 2. When ready to deploy
git checkout deploy/production
git merge main
git push origin deploy/production  # ← Triggers Cloud Build!
```

### Monitor Deployment

Console:
```bash
open "https://console.cloud.google.com/cloud-build/builds?project=YOUR_PROJECT"
```

CLI:
```bash
# Watch ongoing builds
gcloud builds list --ongoing --project=YOUR_PROJECT

# Stream logs for specific build
gcloud builds log BUILD_ID --stream --project=YOUR_PROJECT
```

### Verify Deployment

```bash
# Get Cloud Run URL
gcloud run services describe raglab \
  --region=us-central1 \
  --project=YOUR_PROJECT \
  --format="value(status.url)"

# Test health endpoint
curl https://YOUR_SERVICE_URL/health
```

## Update Configuration

### Update Secrets (No Rebuild)

```bash
# Edit .env
vim .env

# Re-upload to Secret Manager
cd deployment
./upload-secrets.sh

# Restart service to pick up new secrets
gcloud run services update raglab \
  --region=us-central1 \
  --project=YOUR_PROJECT
```

### Update Code (Full Rebuild)

```bash
# Push to deploy branch (triggers build automatically)
git checkout deploy/production
git merge main
git push origin deploy/production
```

## Rollback

### To Previous Revision

```bash
# List revisions
gcloud run revisions list \
  --service=raglab \
  --region=us-central1 \
  --project=YOUR_PROJECT

# Route traffic to previous revision
gcloud run services update-traffic raglab \
  --region=us-central1 \
  --project=YOUR_PROJECT \
  --to-revisions=REVISION_NAME=100
```

## Cost Estimates

**Infrastructure (monthly):**
- Cloud SQL (db-f1-micro): $10-15
- GCS storage: $0.02/GB
- Cloud Run (scales to zero): $0-5
- Secret Manager: $0.06 (within free tier)

**Per Deployment:**
- Cloud Build: ~5 min first build, ~2 min cached
- Cost: $0.02-0.04 (within 120 free build-minutes/day)

## Troubleshooting

### Build Fails: "Secret not found"

```bash
cd deployment
./upload-secrets.sh
```

### Build Fails: "Permission denied"

Check Cloud Build SA has all roles:
```bash
./setup-cloudbuild-trigger.sh  # Re-run to grant permissions
```

### Deployment Succeeds but Service Crashes

Check logs:
```bash
gcloud run services logs read raglab \
  --region=us-central1 \
  --project=YOUR_PROJECT \
  --limit=50
```

Common issues:
- Database connection: Check `DATABASE_URL` in .env
- Missing secrets: Verify secret mounted at `/app/.env`
- Service Account: Check IAM roles for rag-service SA

## Documentation

- **[deployment/CLOUDBUILD_SETUP.md](deployment/CLOUDBUILD_SETUP.md)** - Complete CI/CD setup guide
- **[docs/deployment.md](docs/deployment.md)** - Deployment options and configuration
- **[docs/development.md](docs/development.md)** - Local development setup
- **[docs/dependencies.md](docs/dependencies.md)** - Dependencies architecture

## Support

- GitHub Issues: Report bugs or request features
- Cloud Build logs: Detailed build output
- Cloud Run logs: Runtime errors and debugging
