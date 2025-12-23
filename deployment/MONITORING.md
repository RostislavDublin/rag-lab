# Monitoring Cloud Build Deployments

Complete guide for tracking deployment progress and troubleshooting.

## Quick Start - Monitor Active Deployment

### 1. Check if Build Started

```bash
# List ongoing builds
gcloud builds list --ongoing --project=myai-475419

# Or with more details
gcloud builds list --limit=5 --project=myai-475419 \
  --format="table(id,status,createTime,source.repoSource.branchName)"
```

### 2. Stream Logs in Real-Time

```bash
# Get latest build ID
BUILD_ID=$(gcloud builds list --limit=1 --ongoing --project=myai-475419 --format="value(id)")

# Stream logs
gcloud builds log $BUILD_ID --stream --project=myai-475419
```

**Or one-liner:**
```bash
gcloud builds log $(gcloud builds list --limit=1 --ongoing --project=myai-475419 --format="value(id)") --stream --project=myai-475419
```

### 3. Open Console (Visual)

```bash
# macOS
open "https://console.cloud.google.com/cloud-build/builds?project=myai-475419"

# Linux
xdg-open "https://console.cloud.google.com/cloud-build/builds?project=myai-475419"

# Or just visit in browser:
# https://console.cloud.google.com/cloud-build/builds?project=myai-475419
```

## Detailed Monitoring

### Check Build Status

```bash
# Latest build (any branch)
gcloud builds list --limit=1 --project=myai-475419 \
  --format="table(id,status,createTime,duration,logUrl)"

# Filter by branch
gcloud builds list --limit=5 --project=myai-475419 \
  --filter="source.repoSource.branchName=deploy/production" \
  --format="table(id,status,createTime,duration)"

# Only successful builds
gcloud builds list --filter="status=SUCCESS" --limit=5 --project=myai-475419
```

### Get Specific Build Details

```bash
BUILD_ID="your-build-id"

# Full YAML output
gcloud builds describe $BUILD_ID --project=myai-475419

# Just status and timing
gcloud builds describe $BUILD_ID --project=myai-475419 \
  --format="yaml(id,status,createTime,finishTime,timing)"

# Just steps status
gcloud builds describe $BUILD_ID --project=myai-475419 \
  --format="table(steps.name,steps.status,steps.timing.startTime,steps.timing.endTime)"
```

### View Logs

```bash
BUILD_ID="your-build-id"

# Stream logs (real-time)
gcloud builds log $BUILD_ID --stream --project=myai-475419

# View completed logs
gcloud builds log $BUILD_ID --project=myai-475419

# Last 50 lines only
gcloud builds log $BUILD_ID --project=myai-475419 | tail -50
```

## Understanding Build Progress

### Build Stages

When you see logs, these are the stages (from cloudbuild.yaml):

```
1. "Build Docker image" (5 min first time, 2 min cached)
   - Downloads requirements-base.txt packages
   - Builds Docker image
   - Tags as us-central1-docker.pkg.dev/myai-475419/raglab/raglab:latest

2. "Push image to Artifact Registry" (30 sec)
   - Uploads image to Artifact Registry

3. "Verify secret exists" (5 sec)
   - Checks raglab-config secret in Secret Manager
   - FAILS if secret not uploaded

4. "Deploy to Cloud Run" (1-2 min)
   - Creates new Cloud Run revision
   - Mounts secret as volume
   - Runs health checks
   - Switches traffic to new revision
```

### Expected Output

**Successful build logs:**
```
Starting Step #0 - "Build Docker image"
Step #0: Sending build context to Docker daemon...
Step #0: Step 1/10 : FROM python:3.11-slim
Step #0: Step 2/10 : WORKDIR /app
...
Step #0: Successfully built abc123def456
Step #0: Successfully tagged gcr.io/myai-475419/raglab:latest
Finished Step #0

Starting Step #1 - "Push image to Container Registry"
Step #1: The push refers to repository [gcr.io/myai-475419/raglab]
Step #1: latest: digest: sha256:xyz789 size: 4567
Finished Step #1

Starting Step #2 - "Verify secret exists"
Step #2: ✓ Secret 'raglab-config' exists
Finished Step #2

Starting Step #3 - "Deploy to Cloud Run"
Step #3: Deploying container to Cloud Run service [raglab]...
Step #3: ✓ Deploying... Done.
Step #3:   https://raglab-xyz-uc.a.run.app
Finished Step #3

SUCCESS
```

## Troubleshooting Failed Builds

### Common Errors and Solutions

#### Error 1: "Repository mapping does not exist"

**Symptom:**
```
ERROR: FAILED_PRECONDITION: Repository mapping does not exist
```

**Cause:** GitHub repository not connected to Cloud Build

**Fix:**
```bash
# Re-run setup script
cd deployment
./setup-cloudbuild-trigger.sh
# When prompted, connect GitHub repo in browser
```

#### Error 2: "Secret 'raglab-config' not found"

**Symptom:**
```
Step #2: ERROR: Secret 'raglab-config' not found!
```

**Cause:** .env not uploaded to Secret Manager

**Fix:**
```bash
cd deployment
./upload-secrets.sh
```

#### Error 3: "Permission denied to deploy Cloud Run"

**Symptom:**
```
Step #3: ERROR: (gcloud.run.deploy) Permission denied
```

**Cause:** Cloud Build SA missing IAM roles

**Fix:**
```bash
cd deployment
./setup-cloudbuild-trigger.sh  # Re-grants permissions
```

#### Error 4: "Docker build timeout"

**Symptom:**
```
Step #0: context deadline exceeded
Build timeout: 300s
```

**Cause:** Build took longer than 5 minutes (shouldn't happen with requirements-base.txt)

**Fix:** Check cloudbuild.yaml timeout:
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    timeout: 600s  # Increase if needed
```

#### Error 5: "Service deployment failed"

**Symptom:**
```
Step #3: ERROR: Revision creation failed
```

**Cause:** Application crashed on startup

**Fix:** Check Cloud Run logs:
```bash
gcloud run services logs read raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --limit=50
```

Common startup issues:
- DATABASE_URL incorrect
- Secret not mounted at /app/.env
- Service Account missing permissions

## Monitoring After Deployment

### Check Service Status

```bash
# Get service URL and status
gcloud run services describe raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --format="yaml(status.url,status.conditions)"

# Test health endpoint
SERVICE_URL=$(gcloud run services describe raglab --region=us-central1 --project=myai-475419 --format="value(status.url)")
curl -s $SERVICE_URL/health | jq .
```

### View Runtime Logs

```bash
# Latest logs
gcloud run services logs read raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --limit=50

# Stream new logs
gcloud run services logs tail raglab \
  --region=us-central1 \
  --project=myai-475419

# Filter by severity
gcloud run services logs read raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --filter="severity>=ERROR"
```

### Check Revisions

```bash
# List all revisions
gcloud run revisions list \
  --service=raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --format="table(name,status,trafficPercent,activeRevisions.createTime)"

# Get latest revision
gcloud run revisions list \
  --service=raglab \
  --region=us-central1 \
  --project=myai-475419 \
  --limit=1 \
  --format="value(name)"
```

## Automated Monitoring Script

Save this as `deployment/monitor-build.sh`:

```bash
#!/bin/bash
# Monitor latest Cloud Build deployment

set -e

PROJECT_ID="myai-475419"

echo "Checking for active builds..."
BUILD_ID=$(gcloud builds list --limit=1 --ongoing --project=$PROJECT_ID --format="value(id)" 2>/dev/null)

if [ -z "$BUILD_ID" ]; then
    echo "No active builds. Checking latest build..."
    BUILD_ID=$(gcloud builds list --limit=1 --project=$PROJECT_ID --format="value(id)")
    
    if [ -z "$BUILD_ID" ]; then
        echo "No builds found."
        exit 1
    fi
    
    STATUS=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(status)")
    echo "Latest build: $BUILD_ID"
    echo "Status: $STATUS"
    
    if [ "$STATUS" != "SUCCESS" ]; then
        echo ""
        echo "Build failed! Showing logs:"
        gcloud builds log $BUILD_ID --project=$PROJECT_ID | tail -50
    fi
else
    echo "Active build found: $BUILD_ID"
    echo "Streaming logs..."
    echo ""
    gcloud builds log $BUILD_ID --stream --project=$PROJECT_ID
fi
```

Make executable:
```bash
chmod +x deployment/monitor-build.sh
```

Usage:
```bash
./deployment/monitor-build.sh
```

## Console Dashboard

**Best visual experience:** Cloud Build Console

1. **Builds Overview:**
   https://console.cloud.google.com/cloud-build/builds?project=myai-475419

2. **Triggers:**
   https://console.cloud.google.com/cloud-build/triggers?project=myai-475419

3. **Cloud Run Services:**
   https://console.cloud.google.com/run?project=myai-475419

4. **Cloud Run Logs:**
   https://console.cloud.google.com/run/detail/us-central1/raglab/logs?project=myai-475419

## Quick Reference Commands

```bash
# Start monitoring immediately after push
git push origin deploy/production && gcloud builds list --ongoing --project=myai-475419

# Stream logs of latest build
gcloud builds log $(gcloud builds list --limit=1 --project=myai-475419 --format="value(id)") --stream --project=myai-475419

# Check if deployment succeeded
gcloud builds list --limit=1 --filter="source.repoSource.branchName=deploy/production" --project=myai-475419 --format="value(status)"

# Get deployed service URL
gcloud run services describe raglab --region=us-central1 --project=myai-475419 --format="value(status.url)"

# Test deployed service
curl $(gcloud run services describe raglab --region=us-central1 --project=myai-475419 --format="value(status.url)")/health
```

## Webhook Debugging

If build doesn't start after push:

```bash
# Check trigger exists and is enabled
gcloud builds triggers describe deploy-production \
  --region=us-central1 \
  --project=myai-475419 \
  --format="yaml(disabled,github)"

# Manually trigger build (for testing)
gcloud builds triggers run deploy-production \
  --region=us-central1 \
  --project=myai-475419 \
  --branch=deploy/production
```

## Related Documentation

- [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) - Deployment workflow
- [deployment/CLOUDBUILD_SETUP.md](CLOUDBUILD_SETUP.md) - Initial setup
- [docs/deployment.md](../docs/deployment.md) - Deployment guide
