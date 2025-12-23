# Cloud Build Setup Guide

This guide explains how to set up automated Cloud Build deployment from GitHub.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Developer Workflow                                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. Work on main branch (frequent commits)                      │
│ 2. When ready to deploy:                                        │
│    - Update secrets: ./deployment/upload-secrets.sh (if needed) │
│    - Push to deploy branch: git push origin deploy/production   │
│ 3. Cloud Build automatically builds & deploys                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Cloud Build Process                                             │
├─────────────────────────────────────────────────────────────────┤
│ GitHub (deploy/production) → Cloud Build Trigger →              │
│ Build Docker (20 min) → Push to Artifact Registry → Deploy      │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **GitHub repository** with rag-lab code
2. **Infrastructure deployed:** Run `./deployment/setup-infrastructure.sh`
3. **Secrets uploaded:** Run `./deployment/upload-secrets.sh`

## Setup Steps

### 1. Connect GitHub Repository

```bash
# Enable Cloud Build API
gcloud services enable cloudbuild.googleapis.com --project=YOUR_PROJECT_ID

# Open Cloud Build Triggers in Console
open "https://console.cloud.google.com/cloud-build/triggers?project=YOUR_PROJECT_ID"
```

**In Console:**
1. Click "Connect Repository"
2. Select "GitHub (Cloud Build GitHub App)"
3. Authenticate with GitHub
4. Select your repository: `YourUsername/rag-lab`
5. Click "Connect"

### 2. Create Cloud Build Trigger

**In Console (Cloud Build > Triggers):**

Click "Create Trigger" and configure:

**Basic Info:**
- Name: `deploy-production`
- Description: `Deploy RAG Lab to Cloud Run from deploy/production branch`
- Event: `Push to a branch`
- Repository: `YourUsername/rag-lab (GitHub)`

**Source:**
- Branch: `^deploy/production$` (regex pattern, ONLY this branch)
- Included files filter: `**` (all files)

**Configuration:**
- Type: `Cloud Build configuration file (yaml or json)`
- Location: `Repository`
- Cloud Build configuration file location: `/cloudbuild.yaml`

**Service Account:**
- Service account: `[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`

**Substitution Variables (optional):**
- None needed (uses $PROJECT_ID from environment)

Click "Create"

### 3. Grant Cloud Build Permissions

Cloud Build service account needs permissions to deploy:

```bash
PROJECT_ID="YOUR_PROJECT_ID"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant Cloud Run Admin (deploy service)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" \
  --role="roles/run.admin"

# Grant Service Account User (act as service account)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" \
  --role="roles/iam.serviceAccountUser"

# Grant Secret Manager Accessor (read secrets)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" \
  --role="roles/secretmanager.secretAccessor"

# Grant Artifact Registry Writer (push images to Artifact Registry)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" \
  --role="roles/storage.admin"
```

### 4. Create Deploy Branch

```bash
# Create deploy branch from main
git checkout main
git pull origin main
git checkout -b deploy/production
git push origin deploy/production

# Set up branch protection (optional, in GitHub UI)
# Settings > Branches > Add rule > deploy/production
# - Require pull request reviews
# - Require status checks to pass
```

## Usage

### Initial Deploy

```bash
# 1. Upload secrets (first time only)
cd deployment
./upload-secrets.sh

# 2. Trigger deploy
git checkout main
# ... make changes ...
git commit -m "Ready for deploy"
git push origin main

# 3. Merge to deploy branch
git checkout deploy/production
git merge main
git push origin deploy/production  # Triggers Cloud Build

# 4. Monitor build
open "https://console.cloud.google.com/cloud-build/builds?project=YOUR_PROJECT_ID"
```

### Update Secrets

```bash
# 1. Edit .env locally
vim .env

# 2. Upload to Secret Manager
cd deployment
./upload-secrets.sh

# 3. Redeploy to pick up new secrets
git checkout deploy/production
git push origin deploy/production  # Triggers rebuild
```

### Regular Deploy

```bash
# Work on main as usual
git checkout main
# ... develop features ...
git commit -m "Feature complete"
git push origin main

# When ready to deploy:
git checkout deploy/production
git merge main
git push origin deploy/production  # Triggers Cloud Build
```

## Troubleshooting

### Build Fails: "Secret not found"

```bash
# Upload secrets first
cd deployment
./upload-secrets.sh
```

### Build Timeout

```bash
# Check cloudbuild.yaml timeout settings
# Current: 1800s (30 minutes) total
# Docker build: 1200s (20 minutes)
# Increase if needed (max: 86400s = 24 hours)
```

### Permission Denied

```bash
# Re-run IAM grants for Cloud Build service account
# See "Grant Cloud Build Permissions" section above
```

### Wrong Branch Triggered

Check trigger configuration:
- Branch regex: `^deploy/production$`
- Should NOT match `main`, `develop`, `feature/*`

## Cost Optimization

**Cloud Build Pricing:**
- First 120 build-minutes/day: FREE
- Additional: $0.003/build-minute
- E2_HIGHCPU_8 machine: ~$0.08/hour

**Typical build:**
- Duration: ~15-20 minutes (with caching)
- Cost: ~$0.02-0.04 per deploy
- With free tier: ~4-6 deploys/day free

**Tips:**
- Use caching (already configured in cloudbuild.yaml)
- Deploy from `deploy/production` only (not every commit)
- Use E2_HIGHCPU_8 for faster builds (configured)

## Monitoring

**Cloud Build Logs:**
```bash
# View recent builds
gcloud builds list --limit=10

# Follow specific build
gcloud builds log BUILD_ID --stream
```

**Cloud Run Logs:**
```bash
# After deployment
gcloud run services logs read raglab --region us-central1 --limit 50
```

## Rollback

```bash
# List previous images
gcloud artifacts docker images list us-central1-docker.pkg.dev/YOUR_PROJECT_ID/raglab

# Rollback to previous version
gcloud run deploy raglab \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/raglab/raglab:PREVIOUS_COMMIT_SHA \
  --region us-central1
```
