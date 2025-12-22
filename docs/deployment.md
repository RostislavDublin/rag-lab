# Deployment Guide

This guide covers deploying RAG Lab to Google Cloud Run and other platforms.

## Cloud Run Deployment

### Automated Setup (Recommended)

Complete infrastructure setup and deployment using Python scripts:

```bash
# 1. Configure deployment
cd deployment
cp .env.deploy.example .env.deploy
# Edit .env.deploy with your settings:
#   GCP_PROJECT_ID=your-project-id
#   GCP_REGION=us-central1
#   DEPLOYMENT_AUTH_MODE=gcloud
# 
# For details on .env.deploy vs .env vs .env.local, see:
# docs/development.md#configuration-files

# 2. Setup GCP infrastructure (one-time)
# Creates: Cloud SQL, GCS bucket, Service Account, enables APIs
python setup_infrastructure.py

# This creates:
# - Cloud SQL PostgreSQL 15 with pgvector
# - GCS bucket in same region ($0 egress)
# - Service Account with IAM roles
# - Root .env file with application config (NOT .env.deploy!)
# - deployment/credentials.txt with all info

# 3. Deploy to Cloud Run
python deploy_cloudrun.py

# 4. Test deployment
SERVICE_URL=$(gcloud run services describe rag-api --region us-central1 --format 'value(status.url)')
curl $SERVICE_URL/health
```

### Manual Setup

If you prefer manual control:

```bash
# 1. Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
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

# 5. Deploy
gcloud run deploy rag-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances=PROJECT:REGION:rag-postgres \
  --set-env-vars "GCP_PROJECT_ID=YOUR_PROJECT,GCS_BUCKET=YOUR_BUCKET,DATABASE_URL=postgresql://..."
```

### Cleanup

Remove all infrastructure when done:

```bash
cd deployment
python teardown.py
# Type 'DELETE-ALL' to confirm
```

## Multi-Cloud Portability

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
- sentence-transformers (local, 384 dimensions) - 100% portable, no API costs

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
