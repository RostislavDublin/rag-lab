# RAG Lab - RAG-as-a-Service

Production-ready Retrieval Augmented Generation (RAG) system with:
- **Hybrid storage**: PostgreSQL for embeddings, GCS for documents (8.5x cheaper)
- **UUID-based**: Globally unique, immutable document identifiers
- **Multi-cloud portable**: PostgreSQL + pgvector + GCS works everywhere
- **Cost-effective**: Cloud Run auto-scales to zero ($0-5/month)
- **Efficient chunking**: Separate JSON files for fast RAG queries

## Architecture

```
                    ┌─────────────────┐
                    │  Cloud Run      │
                    │  (FastAPI)      │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┬─────────────────┐
            ▼                ▼                ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Vertex AI   │  │  Cloud SQL   │  │  Cloud       │  │  Gemini API  │
    │  Embeddings  │  │  PostgreSQL  │  │  Storage     │  │  Generation  │
    │  (pluggable) │  │  + pgvector  │  │  (GCS)       │  │  (future)    │
    └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                             │                    │
                       ┌─────┴────────┐   ┌──────┴───────┐
                       │ Embeddings   │   │ Documents    │
                       │ Metadata     │   │ Text         │
                       │ Vector Search│   │ Chunks       │
                       └──────────────┘   └──────────────┘
```

### Hybrid Storage Architecture

**PostgreSQL (Cloud SQL):** Embeddings + Metadata only
```sql
original_documents                 document_chunks
─────────────────                 ────────────────
id                                id
doc_uuid (UUID) ◄─────────┐       original_doc_id (FK) ─┐
filename                  │       embedding (VECTOR)    │
file_type                 │       chunk_index           │
file_size                 │       created_at            │
metadata                  │                             │
chunk_count               │       CASCADE DELETE ◄──────┘
uploaded_at               │
                          │
                          └── UNIQUE, globally unique identifier
```

**Google Cloud Storage:** Documents + Text + Chunks
```
gs://raglab-documents/
└── {doc_uuid}/              # UUID-based flat structure
    ├── document.pdf         # Original PDF file
    ├── extracted.txt        # Full extracted text
    └── chunks/
        ├── 000.json        # {"text": "...", "index": 0, "metadata": {...}}
        ├── 001.json
        └── ...
```

**Why hybrid storage?**
- **PostgreSQL**: Fast vector search on embeddings (5.6KB each)
- **GCS**: Cheap storage for text/files ($0.02/GB vs $0.17/GB)
- **No egress costs**: Cloud Run + GCS in same region = $0 egress
- **Efficient RAG**: Fetch only needed chunks (3-5) not all 50
- **Regeneration**: Keep extracted text for re-embedding without re-processing PDFs

## Quick Start (Local Development)

### 1. Prerequisites

```bash
# Install Docker & Docker Compose
docker --version
docker-compose --version

# GCP credentials for Vertex AI + GCS
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
export GCP_PROJECT_ID=your-project-id

# Create GCS bucket (same region as Cloud Run for $0 egress)
gcloud storage buckets create gs://raglab-documents \
  --location=us-central1 \
  --uniform-bucket-level-access

# Set environment variable
export GCS_BUCKET=raglab-documents
```

### 2. Start Services

```bash
# Start PostgreSQL + API
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### 3. Test API

```bash
# Health check
curl http://localhost:8080/health

# Upload PDF document
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@sample.pdf"

# Query RAG system
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is RAG?",
    "top_k": 3
  }'

# Generate embeddings (direct)
curl -X POST http://localhost:8080/v1/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

## API Endpoints

### `POST /v1/documents/upload`

Upload and process PDF document.

**Request:**
```bash
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@document.pdf"
```

**Response:**
```json
{
  "doc_id": 1,
  "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "chunks_created": 42,
  "message": "Document processed successfully: 42 chunks created"
}
```

**What happens:**
1. Extract text from PDF (PyMuPDF)
2. Create database record → get UUID
3. Chunk text (500 chars, 50 overlap)
4. Generate embeddings (Vertex AI text-embedding-005)
5. Upload to GCS in parallel: PDF + extracted text + all chunk JSONs
6. Store only embeddings in PostgreSQL
7. Update chunk count in database

### `POST /v1/query`

Query RAG system with natural language.

**Request:**
```bash
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is RAG?",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "query": "What is RAG?",
  "total": 3,
  "results": [
    {
      "chunk_text": "RAG (Retrieval Augmented Generation) is...",
      "similarity": 0.89,
      "chunk_index": 5,
      "filename": "paper.pdf",
      "original_doc_id": 1,
      "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "doc_metadata": {}
    }
  ]
}
```

**What happens:**
1. Generate query embedding (Vertex AI)
2. Vector search in PostgreSQL (cosine similarity)
3. Group results by doc_uuid for efficient GCS fetching
4. Fetch chunk texts from GCS in parallel
5. Merge texts with search results
6. Return formatted response with full chunk context

### `POST /v1/embed`

Generate embeddings directly (for testing).

**Request:**
```bash
curl -X POST http://localhost:8080/v1/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

**Response:**
```json
{
  "embedding": [0.123, -0.456, ...],
  "dimension": 1408
}
```

### `GET /health`

Health check for Cloud Run.

**Response:**
```json
{
  "status": "healthy",
  "project_id": "your-project-id",
  "location": "us-central1"
}
```

## Cloud Run Deployment

### Prerequisites

```bash
# Install gcloud CLI
gcloud --version

# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  aiplatform.googleapis.com
```

### 1. Create Cloud SQL PostgreSQL Instance

```bash
# Create instance with pgvector
gcloud sql instances create raglab-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1

# Create database
gcloud sql databases create raglab --instance=raglab-db

# Create user
gcloud sql users create raglab \
  --instance=raglab-db \
  --password=SECURE_PASSWORD
```

### 2. Create GCS Bucket (Same Region)

```bash
# Create bucket in same region for $0 egress
gcloud storage buckets create gs://raglab-documents \
  --location=us-central1 \
  --uniform-bucket-level-access

# Grant Cloud Run service account access
gcloud storage buckets add-iam-policy-binding gs://raglab-documents \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

### 3. Deploy to Cloud Run

```bash
# Option 1: Use deployment script
cd deployment
chmod +x deploy-cloudrun.sh
./deploy-cloudrun.sh

# Option 2: Manual deployment
gcloud run deploy raglab \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=YOUR_PROJECT,GCS_BUCKET=raglab-documents,DATABASE_URL=postgresql://..."
```

### 4. Test Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe raglab --region us-central1 --format 'value(status.url)')

# Test health
curl $SERVICE_URL/health

# Upload document
curl -X POST $SERVICE_URL/v1/documents/upload \
  -F "file=@sample.pdf"
```

## Configuration

### Environment Variables

**Required:**
- `GCP_PROJECT_ID`: Google Cloud project ID
- `GCS_BUCKET`: Cloud Storage bucket name (e.g., raglab-documents)
- `DATABASE_URL`: PostgreSQL connection string

**Optional:**
- `GCP_LOCATION`: Vertex AI region (default: us-central1)
- `PORT`: Server port (default: 8080)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key

**CRITICAL:** Deploy Cloud Run and GCS bucket in **same region** (e.g., us-central1) for $0 egress costs

### Database Connection String Format

```bash
# Cloud SQL with private IP
DATABASE_URL=postgresql://user:pass@10.1.2.3:5432/raglab

# Cloud SQL with Unix socket
DATABASE_URL=postgresql://user:pass@/cloudsql/project:region:instance/raglab

# Local development
DATABASE_URL=postgresql://raglab:password@localhost:5432/raglab
```

## Multi-Cloud Portability

### Storage (PostgreSQL + pgvector)

**Works on:**
- GCP: Cloud SQL for PostgreSQL
- AWS: Amazon RDS for PostgreSQL
- Azure: Azure Database for PostgreSQL
- Self-hosted: Any PostgreSQL 12+ with pgvector extension

### Embeddings (Pluggable Providers)

**Current:** Vertex AI text-embedding-005 (1408 dimensions)

**Alternative:** sentence-transformers (local, 384 dimensions)

**To switch providers:**
1. Update `document_processor.py` initialization
2. **Regenerate all embeddings** (different dimensions)
3. Fetch extracted text from GCS to avoid re-processing PDFs
4. Update embeddings in PostgreSQL

```python
# Change in src/main.py
document_processor = DocumentProcessor(
    provider=EmbeddingProvider.SENTENCE_TRANSFORMERS  # 100% portable
)

# Regeneration workflow:
# 1. Fetch extracted.txt from GCS: gs://{bucket}/{doc_uuid}/extracted.txt
# 2. Re-chunk and embed with new provider
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

## Development Workflow

### 1. Local Development

```bash
# Start services
docker-compose up -d

# Edit code (hot reload enabled)
vim src/main.py

# View logs
docker-compose logs -f api

# Test changes
curl http://localhost:8080/health
```

### 2. Database Access

```bash
# Connect to PostgreSQL
docker exec -it raglab-postgres psql -U raglab -d raglab

# Query documents (metadata only, no file content)
SELECT id, doc_uuid, filename, chunk_count, uploaded_at FROM original_documents;

# Query chunks (embeddings only, no text)
SELECT COUNT(*) FROM document_chunks;
SELECT original_doc_id, chunk_index FROM document_chunks LIMIT 5;

# Vector search test (returns chunk_index to fetch from GCS)
SELECT dc.chunk_index, od.doc_uuid, 
       1 - (dc.embedding <=> '[0,0,...]'::vector) as similarity
FROM document_chunks dc
JOIN original_documents od ON dc.original_doc_id = od.id
ORDER BY dc.embedding <=> '[0,0,...]'::vector
LIMIT 3;

# Check GCS paths
SELECT doc_uuid, 
       CONCAT('gs://raglab-documents/', doc_uuid, '/document.pdf') as pdf_path,
       CONCAT('gs://raglab-documents/', doc_uuid, '/chunks/000.json') as chunk_path
FROM original_documents;
```

### 3. Run Tests

```bash
# Unit tests (future)
pytest tests/

# Integration tests
python scripts/test_api.py
```

## Project Structure

```
rag-lab/
├── src/
│   ├── main.py              # FastAPI application (upload + query endpoints)
│   ├── database.py          # PostgreSQL + pgvector (embeddings only)
│   ├── storage.py           # Cloud Storage (documents + text + chunks)
│   ├── document_processor.py # PDF to chunks to embeddings
│   └── __init__.py
├── deployment/
│   ├── deploy-cloudrun.sh   # Automated Cloud Run deployment
│   ├── test-deployment.sh   # Test deployed service
│   └── local-run.sh         # Run Docker container locally
├── Dockerfile               # Multi-stage production build
├── docker-compose.yaml      # Local development stack
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Troubleshooting

### Database Connection Failed

```bash
# Check PostgreSQL is running
docker-compose ps

# Check logs
docker-compose logs postgres

# Test connection
psql $DATABASE_URL
```

### Vertex AI Authentication Failed

```bash
# Check credentials
echo $GOOGLE_APPLICATION_CREDENTIALS
cat $GOOGLE_APPLICATION_CREDENTIALS

# Set project ID
export GCP_PROJECT_ID=your-project-id

# Test gcloud auth
gcloud auth list
```

### Cloud Run Deployment Failed

```bash
# Check service logs
gcloud run services logs read raglab --region us-central1

# Check environment variables
gcloud run services describe raglab --region us-central1

# Redeploy
cd deployment
./deploy-cloudrun.sh
```

## Next Steps

- [ ] Document download endpoint: `GET /v1/documents/{uuid}/download` (GCS signed URL)
- [ ] Document deletion endpoint: `DELETE /v1/documents/{uuid}` (GCS + DB cleanup)
- [ ] Add Gemini integration for answer generation
- [ ] Implement authentication (API keys, OAuth)
- [ ] Add rate limiting
- [ ] Implement monitoring and logging
- [ ] Add support for more file types (TXT, DOCX, etc.)
- [ ] Create Kubernetes manifests for GKE
- [ ] Add comprehensive tests
- [ ] Add search result ranking
- [ ] Implement Redis caching for hot chunks (reduce GCS calls)

## License

MIT

## Contributing

PRs welcome! This is a learning project exploring production RAG architectures.
