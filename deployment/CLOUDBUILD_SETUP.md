# Cloud Build Trigger Setup

Automated setup for GitHub → Cloud Build → Cloud Run deployment pipeline.

## Overview

This script automates:
1. ✅ GitHub repository connection verification
2. ✅ Cloud Build API enablement
3. ✅ Cloud Build Trigger creation
4. ✅ IAM permissions for Cloud Build Service Account
5. ✅ Deployment readiness check

## Prerequisites

1. **Infrastructure deployed:**
   ```bash
   cd deployment
   ./setup-infrastructure.sh
   ```

2. **Secrets uploaded:**
   ```bash
   cd deployment
   ./upload-secrets.sh
   ```

3. **Configuration file:**
   ```bash
   cp .env.deploy.example .env.deploy
   # Edit .env.deploy with your settings
   ```

## Configuration

Add to `deployment/.env.deploy`:

```bash
# GitHub repository
GITHUB_REPO_OWNER="YourGitHubUsername"
GITHUB_REPO_NAME="rag-lab"

# Cloud Build trigger
TRIGGER_NAME="deploy-production"
DEPLOY_BRANCH="deploy/production"
```

## Usage

### One-Time Setup

```bash
cd deployment
./setup-cloudbuild-trigger.sh
```

**The script will:**

1. **Check prerequisites** (project ID, region, GitHub settings)

2. **Prompt for GitHub connection:**
   - Opens Console link
   - Wait for you to connect GitHub repo (OAuth, one-time)
   - Press Enter to continue

3. **Create Cloud Build Trigger:**
   - Name: `deploy-production`
   - Branch pattern: `^deploy/production$` (regex, only this branch)
   - Build config: `cloudbuild.yaml`
   - Service Account: `[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`

4. **Grant IAM permissions:**
   - `roles/run.admin` - Deploy to Cloud Run
   - `roles/iam.serviceAccountUser` - Act as rag-service SA
   - `roles/secretmanager.secretAccessor` - Read secrets
   - `roles/artifactregistry.writer` - Push images to Artifact Registry

5. **Verify setup** and show next steps

## What Gets Created

### Cloud Build Service Account

**Email:** `[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`

**Auto-created:** When Cloud Build API is enabled (first use)

**Purpose:** Build and deploy (deployment time only)

**Permissions:**
```bash
roles/run.admin                    # Deploy Cloud Run service
roles/iam.serviceAccountUser       # Delegate to rag-service SA
roles/secretmanager.secretAccessor # Verify secrets exist
roles/artifactregistry.writer      # Push Docker images to Artifact Registry
```

### Cloud Build Trigger

**Name:** `deploy-production` (from TRIGGER_NAME)

**Event:** Push to `deploy/production` branch

**Action:** Execute `cloudbuild.yaml`

**Steps:**
1. Build Docker image → `REGION-docker.pkg.dev/PROJECT/raglab/raglab:latest`
2. Push to Artifact Registry
3. Verify secret exists (fail fast)
4. Deploy to Cloud Run with secret mounted

## GitHub Connection (One-Time Manual Step)

**Why manual?** OAuth authentication requires browser interaction (cannot be automated).

**How to connect:**

1. Script opens: `https://console.cloud.google.com/cloud-build/triggers?project=YOUR_PROJECT`
2. Click "Connect Repository"
3. Select "GitHub (Cloud Build GitHub App)"
4. Authenticate with GitHub (OAuth)
5. Grant access to repository: `YourUsername/rag-lab`
6. Click "Connect"
7. Return to terminal and press Enter

**This is done ONCE.** Future triggers use the same connection.

## Verification

After setup, verify configuration:

```bash
# Check trigger exists
gcloud builds triggers describe deploy-production --project=myai-475419

# Check Cloud Build SA has permissions
PROJECT_NUMBER=$(gcloud projects describe myai-475419 --format="value(projectNumber)")
gcloud projects get-iam-policy myai-475419 \
  --flatten="bindings[].members" \
  --filter="bindings.members:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Expected roles:
- roles/iam.serviceAccountUser
- roles/run.admin
- roles/secretmanager.secretAccessor
- roles/storage.admin

## Usage After Setup

### Create Deploy Branch

```bash
git checkout main
git pull origin main
git checkout -b deploy/production
git push origin deploy/production
```

### Deploy Application

```bash
# Work on main branch
git checkout main
# ... make changes ...
git commit -m "Add new feature"
git push origin main

# When ready to deploy
git checkout deploy/production
git merge main
git push origin deploy/production  # ← Triggers Cloud Build!
```

### Monitor Deployment

```bash
# Open Cloud Build console
open "https://console.cloud.google.com/cloud-build/builds?project=myai-475419"

# Or watch in terminal
gcloud builds list --project=myai-475419 --ongoing

# View specific build
gcloud builds log <BUILD_ID> --project=myai-475419 --stream
```

## Troubleshooting

### Error: "Repository not found"

**Cause:** GitHub repository not connected to Cloud Build

**Fix:**
1. Open Cloud Build console
2. Connect repository manually (see "GitHub Connection" section above)
3. Re-run script

### Error: "Permission denied"

**Cause:** Cloud Build SA missing IAM roles

**Fix:**
```bash
# Re-run IAM grants
PROJECT_NUMBER=$(gcloud projects describe myai-475419 --format="value(projectNumber)")
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding myai-475419 \
  --member="serviceAccount:$CB_SA" \
  --role="roles/run.admin"

# Repeat for other roles...
```

### Error: "Secret not found"

**Cause:** .env not uploaded to Secret Manager

**Fix:**
```bash
cd deployment
./upload-secrets.sh
```

### Build succeeds but deploy fails

**Check:**
1. Secret mounted correctly: `--add-volume=name=config,type=secret,secret-name=raglab-config`
2. Cloud SQL instance name: `--add-cloudsql-instances=PROJECT:REGION:INSTANCE`
3. Service account: `--service-account=rag-service@PROJECT.iam.gserviceaccount.com`

**Debug:**
```bash
# Check Cloud Run logs
gcloud run services logs read raglab --project=myai-475419 --region=us-central1
```

## Script Updates

If you change GitHub repo or trigger settings:

```bash
# Update .env.deploy
vim deployment/.env.deploy

# Re-run setup (will update existing trigger)
./deployment/setup-cloudbuild-trigger.sh
```

## Cost

**Cloud Build:**
- Free tier: 120 build-minutes/day
- Each build: ~5 minutes (first) / 2 minutes (cached)
- Cost after free tier: $0.003/build-minute
- **Your cost:** ~$0.01-0.04 per deploy (within free tier for ~24-40 deploys/day)

**Storage (GCR):**
- Images: ~400MB each
- Storage: $0.026/GB/month
- **Your cost:** ~$0.01/month (overwrites latest tag, no accumulation)

**Cloud Build SA:**
- Free (auto-created, no charges)

## Related Documentation

- [cloudbuild.yaml](../cloudbuild.yaml) - Build configuration
- [Deployment Guide](../docs/deployment.md) - Full deployment process
- [Cloud Build Setup](../docs/cloudbuild-setup.md) - Manual setup steps (deprecated)
