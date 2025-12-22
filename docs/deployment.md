# Deployment Guide

This guide covers deploying RAG Lab to Google Cloud Run and other platforms.

## Cloud Run Deployment

### Automated Deployment via GitHub CI/CD (Recommended)

Complete CI/CD pipeline from GitHub → Cloud Build → Cloud Run.

**One-time setup (5 minutes):**

```bash
# 1. Setup infrastructure (one-time)
cd deployment
cp .env.deploy.example .env.deploy
# Edit .env.deploy with your GCP project ID, region, and GitHub repo info

# Run infrastructure setup
./setup-infrastructure.sh
# Creates: Cloud SQL, GCS bucket, Service Account, IAM roles

# 2. Setup Cloud Build trigger (one-time)
./setup-cloudbuild-trigger.sh
# Creates: Cloud Build trigger, GitHub connection, IAM permissions
# Note: Requires one manual step - connecting GitHub repo via browser (OAuth)

# 3. Prepare application configuration
cd ..
cp .env.example .env
# Edit .env with all application settings (embedding models, reranking, auth, secrets)

# Upload secrets to Secret Manager
cd deployment
./upload-secrets.sh
# Uploads .env to Secret Manager (encrypted, versioned)

# 4. Create deploy branch
cd ..
git checkout -b deploy/production
git push origin deploy/production
```

**Regular deployment workflow:**

```bash
# Work on main branch
git checkout main
# ... make changes, commit ...
git push origin main

# When ready to deploy
git checkout deploy/production
git merge main
git push origin deploy/production  # ← Triggers Cloud Build automatically!

# Monitor deployment
open "https://console.cloud.google.com/cloud-build/builds?project=YOUR_PROJECT"
```

**What happens on push to deploy/production:**
1. GitHub webhook triggers Cloud Build
2. Build Docker image (~5 min first time, ~2 min cached)
3. Push to Container Registry
4. Deploy to Cloud Run with secrets mounted
5. Service available at Cloud Run URL

**See [deployment/CLOUDBUILD_SETUP.md](../deployment/CLOUDBUILD_SETUP.md) for complete documentation.**

---

### Manual Deployment (Alternative)

For testing or one-off deployments:

```bash
# After infrastructure setup
cd deployment
./deploy-cloudrun.sh

# This will:
# - Upload .env to Secret Manager
# - Build Docker image with Cloud Build (~5 minutes)
# - Deploy to Cloud Run
# - Test health endpoint
```

### Configuration Files

**See [Configuration Files](development.md#configuration-files) for detailed explanation.**

**Quick reference:**
- `.env.local` - Local development (localhost DB connection)
- `.env` - Production runtime (uploaded to Secret Manager, mounted in Cloud Run)
- `deployment/.env.deploy` - Deployment process (GCP project, region, Cloud Run settings)

### How Configuration Works in Production

**Key principle**: Application reads from `.env` file the same way locally and in Cloud Run.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Local Development                                                   │
├─────────────────────────────────────────────────────────────────────┤
│ .env.local (on disk) → Application reads via python-dotenv          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Production (Cloud Run)                                              │
├─────────────────────────────────────────────────────────────────────┤
│ 1. DevOps uploads .env to Secret Manager (during deploy)           │
│ 2. Secret Manager mounts as volume → /app/.env (at runtime)        │
│ 3. Application reads /app/.env via python-dotenv                    │
└─────────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ Secrets not included in Docker image
- ✅ Configuration updated without rebuilding container
- ✅ Same code path for local and production
- ✅ Platform-portable (Secret Manager is GCP-specific, but app code is not)

**Updating configuration in production:**
```bash
# Edit .env with new values
vim .env

# Re-run deploy script (only updates secret and redeploys, no rebuild)
cd deployment
./deploy-cloudrun.sh
```

**Secret Manager costs:**
- Storage: $0.06/month per active secret version
- Access: $0.03 per 10,000 operations
- Free tier: 6 secrets free
- **Your cost**: ~$0.06/month (within free tier)

### Manual Setup

If you prefer manual control:

```bash
# 1. Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com

# 2. Create Cloud SQL (takes 5-10 minutes)
gcloud sql instances create rag-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --no-backup

# 3. Create database and user
gcloud sql databases create rag_db --instance=rag-postgres
gcloud sql users create rag_user \
  --instance=rag-postgres \
  --password=YOUR_SECURE_PASSWORD

# 4. Create GCS bucket (same region for $0 egress)
gcloud storage buckets create gs://YOUR_PROJECT_ID-rag-documents \
  --location=us-central1 \
  --uniform-bucket-level-access

# 5. Create Secret Manager secret with .env file
gcloud secrets create raglab-config \
  --data-file=.env \
  --replication-policy=automatic

# 6. Create service account and grant permissions
gcloud iam service-accounts create rag-service
SA_EMAIL="rag-service@YOUR_PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudsql.client"
  
gcloud secrets add-iam-policy-binding raglab-config \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"

# 7. Build and deploy
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/raglab:latest

gcloud run deploy raglab \
  --image gcr.io/YOUR_PROJECT_ID/raglab:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account $SA_EMAIL \
  --add-cloudsql-instances=YOUR_PROJECT_ID:us-central1:rag-postgres \
  --add-volume name=config,type=secret,secret-name=raglab-config \
  --add-volume-mount volume=config,mount-path=/app/.env \
  --memory 1Gi \
  --cpu 1
```

### Cleanup

Remove all infrastructure when done:

```bash
cd deployment

# Option 1: Automated teardown (if you have teardown script)
python teardown.py
# Type 'DELETE-ALL' to confirm

# Option 2: Manual cleanup
# Delete Cloud Run service
gcloud run services delete raglab --region us-central1

# Delete Secret Manager secret
gcloud secrets delete raglab-config

# Delete Cloud SQL instance
gcloud sql instances delete rag-postgres

# Delete GCS bucket
gcloud storage rm -r gs://YOUR_PROJECT_ID-rag-documents

# Delete service account
gcloud iam service-accounts delete rag-service@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

## Platform Portability

### Configuration Strategy

RAG Lab uses **volume-mounted configuration files** for maximum portability:

```python
# Application code (platform-agnostic)
from dotenv import load_dotenv
load_dotenv()  # Reads .env from current directory
```

**Platform-specific delivery mechanisms:**
- **Local**: `.env.local` on disk
- **GCP Cloud Run**: `.env` from Secret Manager → volume mount
- **Kubernetes**: `.env` from Secret → volumeMount
- **AWS ECS**: `.env` from SSM Parameter Store → volume
- **Docker Compose**: `.env` via bind mount

✅ **Same application code across all platforms**  
✅ **No cloud-specific SDKs in application code**  
✅ **Easy migration between platforms**

### Storage (PostgreSQL + pgvector)

**Works on:**
- GCP: Cloud SQL for PostgreSQL
- AWS: Amazon RDS for PostgreSQL
- Azure: Azure Database for PostgreSQL
- Self-hosted: Any PostgreSQL 12+ with pgvector extension

### Embeddings (Pluggable Providers)

**Current:** Vertex AI text-embedding-005 (768 dimensions)

**Implementation:** Uses new `google-genai` SDK (replaces deprecated `vertexai.language_models`)

**Why text-embedding-005?** Specialized model for English and code tasks with excellent performance. Using 768 dimensions provides good quality while keeping storage costs reasonable.

**Alternatives:**
- gemini-embedding-001 (up to 3072 dimensions) - latest unified model, superior quality, supports multilingual
- text-embedding-004 (768 dimensions) - older stable model
- sentence-transformers (on-premise, 384 dimensions) - 100% portable, no API costs

**Note:** sentence-transformers requires `requirements-optional.txt` (adds torch ~150MB). Production Dockerfile uses only `requirements-base.txt` by default (Vertex AI providers). For on-premise deployment, uncomment optional dependencies in Dockerfile.

**To upgrade to gemini-embedding-001:**
- Same 768 dimensions: drop-in replacement, no schema changes needed
- Higher dimensions (1024-3072): better quality, requires recreating vector tables and re-embedding all documents

**To switch providers:**
1. Update embedding model in `main.py` (genai_client initialization)
2. Update vector dimension in `database.py` schema
3. **Regenerate all embeddings** (different dimensions require new vectors)
4. Fetch extracted text from GCS to avoid re-processing files
5. Update embeddings in PostgreSQL

```python
# Change in src/main.py
from google import genai

genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# For embeddings - use genai_client.models.embed_content()
response = genai_client.models.embed_content(
    model="text-embedding-005",  # or "gemini-embedding-001"
    contents=text,
)
embedding_vector = response.embeddings[0].values
embedding_dimension = 768  # text-embedding-005

# Update database.py
CREATE TABLE document_chunks (
    embedding VECTOR(768) NOT NULL,  # Match new dimension
    ...
)

# Regeneration workflow:
# 1. Fetch extracted.txt from GCS: gs://{bucket}/{doc_uuid}/extracted.txt
# 2. Re-chunk and embed with new provider (using genai_client)
# 3. Update embeddings in PostgreSQL
```

### Container Migration (Cloud Run to GKE)

**Same Docker container works on:**
- Cloud Run (serverless, auto-scale)
- Google Kubernetes Engine (GKE)
- Any Kubernetes cluster (AWS EKS, Azure AKS, self-hosted)

**Migration steps:**
1. Use existing Dockerfile (no changes)
2. Push image to container registry
3. Deploy to GKE with k8s manifests
4. Update DATABASE_URL to point to PostgreSQL

## Cost Estimates

### Cloud Run + Cloud SQL + GCS (Starter)

- **Cloud Run**: $0-5/month (scale to zero when idle)
- **Cloud SQL (db-f1-micro)**: $7/month (shared CPU, 0.6GB RAM)
  - Stores only embeddings: ~5.6KB per chunk
  - 10k docs × 50 chunks = 500k chunks = 2.8GB embeddings
- **Cloud Storage**: $0.02/GB/month (Standard Storage)
  - 10k PDFs (avg 1MB) = 10GB = $0.20/month
  - Extracted texts + chunks = 5GB = $0.10/month
  - **Egress: $0** (Cloud Run + GCS in same region)
- **Vertex AI Embeddings**: ~$0.00001 per 1000 chars
  - 10k docs × 50 chunks × 500 chars = $0.25 one-time

**Total: ~$7-12/month for 10k documents**

**Why GCS saves money:**
- PostgreSQL: $0.17/GB vs GCS: $0.02/GB (8.5x cheaper)
- Embeddings (5.6KB) must be in DB for vector search
- Text/files (1MB PDFs) belong in object storage

### GKE (Production)

- **GKE Cluster**: $70+/month (autopilot or standard)
- **Cloud SQL (db-n1-standard-1)**: $50+/month
- **GCS**: Same $0.02/GB pricing (scales to millions of documents)
- **Better for:** High traffic, multiple services, complex workloads

## Infrastructure Requirements

**CRITICAL:** Deploy Cloud Run and GCS bucket in **same region** (e.g., us-central1) for $0 egress costs

### Minimum Requirements

- **Cloud Run**: 512MB memory, 1 vCPU
- **Cloud SQL**: db-f1-micro (0.6GB RAM, shared CPU)
- **GCS**: Standard storage class

### Production Recommendations

- **Cloud Run**: 2GB memory, 2 vCPU, min instances = 1
- **Cloud SQL**: db-custom-2-7680 (2 vCPU, 7.5GB RAM)
- **GCS**: Standard storage with lifecycle policies

## Monitoring and Logging

### Cloud Run Logs

```bash
# View application logs
gcloud run services logs read rag-api --region us-central1 --limit 50

# Follow logs in real-time
gcloud run services logs tail rag-api --region us-central1

# Filter by severity
gcloud run services logs read rag-api --region us-central1 --log-filter='severity>=ERROR'
```

### Cloud SQL Monitoring

```bash
# Check instance status
gcloud sql operations list --instance=rag-postgres

# View slow queries
gcloud sql operations describe OPERATION_ID --instance=rag-postgres
```

### GCS Usage

```bash
# Check bucket size
gsutil du -sh gs://your-bucket-name

# List objects by size
gsutil ls -lh gs://your-bucket-name/**
```

## Troubleshooting Deployment

### Cloud Run Deployment Failed

```bash
# Check service logs
gcloud run services logs read rag-api --region us-central1

# Check environment variables
gcloud run services describe rag-api --region us-central1

# Redeploy
cd deployment
python deploy_cloudrun.py
```

### Cloud SQL Connection Issues

```bash
# Test connection from Cloud Run
gcloud run services update rag-api \
  --set-env-vars "DATABASE_URL=postgresql://user:pass@/cloudsql/PROJECT:REGION:INSTANCE/rag_db"

# Check IAM permissions
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:*"
```

### GCS Access Denied

```bash
# Grant service account access
gsutil iam ch serviceAccount:SA_EMAIL:objectAdmin gs://BUCKET_NAME

# Verify permissions
gsutil iam get gs://BUCKET_NAME
```
