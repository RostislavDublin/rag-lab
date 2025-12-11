# RAG Lab - RAG-as-a-Service

Production-ready Retrieval Augmented Generation (RAG) system with:
- **Hybrid storage**: PostgreSQL for embeddings, GCS for documents (8.5x cheaper)
- **UUID-based**: Globally unique, immutable document identifiers
- **Deduplication**: SHA256 file hashing prevents duplicate uploads
- **Multi-format support**: PDF and TXT files
- **Multi-cloud portable**: PostgreSQL + pgvector + GCS works everywhere
- **Cost-effective**: Cloud Run auto-scales to zero ($0-5/month)
- **Local development**: Fast iteration with Cloud SQL Proxy and hot reload

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
filename                  │       embedding (VECTOR(768))│
file_type                 │       chunk_index           │
file_size                 │       created_at            │
file_hash (SHA256) UNIQUE │                             │
metadata                  │       CASCADE DELETE ◄──────┘
chunk_count               │
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

### Deduplication

Documents are deduplicated using SHA256 file hashing:

**How it works:**
1. Calculate SHA256 hash of uploaded file content
2. Check `original_documents.file_hash` (UNIQUE constraint)
3. If duplicate found: return existing document info, skip processing
4. If new: proceed with extraction, chunking, embedding

**Benefits:**
- Prevents wasted processing (no re-extraction, re-embedding)
- Saves storage (no duplicate files in GCS)
- Maintains referential integrity (same content = same UUID)
- Fast check (indexed hash lookup)

**Example:**
```bash
# First upload
curl -X POST http://localhost:8080/v1/documents/upload -F "file=@doc.pdf"
# → Processes document, creates chunks

# Duplicate upload (same content, different filename)
curl -X POST http://localhost:8080/v1/documents/upload -F "file=@doc_copy.pdf"
# → Returns: "Document already exists (uploaded as 'doc.pdf'). Skipping duplicate."
```

**Note:** Deduplication is content-based, not filename-based. Same content with different names = duplicate.

## Quick Start (Local Development)

### Option 1: Local Development with uvicorn (Recommended)

**Prerequisites:**

1. **Create `.env.local` file** (required!):
   ```bash
   cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab
   cp .env.local.example .env.local
   # Edit .env.local with real values:
   # - DATABASE_URL (PostgreSQL connection string)
   # - GCP_PROJECT_ID
   # - GCS_BUCKET_NAME
   # - Other required vars
   ```

2. **Setup virtual environment** (one-time):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

**Start Server:**

```bash
# Navigate to project root
cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab

# Activate virtual environment
source .venv/bin/activate

# Start uvicorn with hot reload
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# Server runs at http://localhost:8080
# Swagger UI at http://localhost:8080/docs
# Code changes auto-reload (no restart needed!)
```

**One-liner:**
```bash
cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab && source .venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

### Option 2: Using deployment script

Fast iteration with Cloud SQL Proxy and hot reload:

```bash
# 1. Setup infrastructure (one-time)
cd deployment
cp .env.deploy.example .env.deploy
# Edit .env.deploy with your GCP_PROJECT_ID and GCP_REGION

# Create GCP resources (Cloud SQL, GCS, Service Account)
python setup_infrastructure.py

# 2. Start local development server
python local_run.py

# Server runs at http://localhost:8080 with hot reload
# Connects to Cloud SQL via proxy
# Uses real Vertex AI embeddings
# Stores documents in GCS
```

**Benefits:**
- Hot reload: code changes apply instantly
- Real infrastructure: same as production
- Fast iteration: no Docker builds
- Cloud SQL Proxy: automatic connection

### Option 3: Docker Compose (Fully Local)

```bash
# Start PostgreSQL + API
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Test API

```bash
# Health check
curl http://localhost:8080/health

# Upload PDF document
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@sample.pdf"

# Upload TXT document
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@document.txt"

# Try uploading duplicate (will be rejected)
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@sample.pdf"
# Response: "Document already exists... Skipping duplicate."

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

### Test with Fixtures

The repository includes 4 test documents (22.6KB total) for integration testing:

```bash
# Upload test documents
for file in tests/fixtures/documents/*.txt; do
  curl -X POST http://localhost:8080/v1/documents/upload \
    -F "file=@$file"
done

# Test queries
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?", "top_k": 5}'

curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How does HNSW indexing work?", "top_k": 5}'
```

## API Endpoints

### `POST /v1/documents/upload`

Upload and process PDF or TXT document. Automatically detects and rejects duplicates.

**Supported formats:** PDF, TXT

**Request:**
```bash
# PDF file
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@document.pdf"

# TXT file
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@document.txt"
```

**Response (new document):**
```json
{
  "doc_id": 1,
  "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "chunks_created": 42,
  "message": "Document processed successfully: 42 chunks created"
}
```

**Response (duplicate detected):**
```json
{
  "doc_id": 1,
  "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "chunks_created": 0,
  "message": "Document already exists (uploaded as 'document.pdf'). Skipping duplicate."
}
```

**What happens:**
1. Calculate SHA256 hash of file content
2. Check database for existing hash (deduplication)
3. If duplicate: return existing document info, skip processing
4. If new: Extract text (PyMuPDF for PDF, UTF-8 decode for TXT)
5. Create database record → get UUID
6. **Chunk text** - balanced chunking for RAG quality:
   - **chunk_size: 2000 chars** (~500 tokens) - optimal balance between context and precision
   - **chunk_overlap: 200 chars** - preserves continuity across boundaries
   - Uses recursive text splitting (paragraphs → sentences → words)
7. **Generate embeddings** (Vertex AI text-embedding-005, 768 dimensions):
   - Parallel processing (max 10 concurrent API calls)
   - **Retry-on-error with smart splitting:**
     - If chunk exceeds token limit (very rare with 2000 chars) → split at semantic boundary
     - Recursively creates 2+ smaller chunks instead of averaging
     - Returns separate (text, embedding) pairs for each sub-chunk
     - Ensures: **#chunks = #embeddings** (always synchronized)
   - Model supports up to 20,000 tokens (our 2000 chars ≈ 500 tokens → safe margin)
8. Upload to GCS in parallel: file + extracted text + all chunk JSONs
9. Store embeddings + file_hash in PostgreSQL
10. Update chunk count in database

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
  "dimension": 768
}
```

**Model:** Vertex AI text-embedding-005 (768 dimensions)

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

# 2. Setup GCP infrastructure (one-time)
# Creates: Cloud SQL, GCS bucket, Service Account, enables APIs
python setup_infrastructure.py

# This creates:
# - Cloud SQL PostgreSQL 15 with pgvector
# - GCS bucket in same region ($0 egress)
# - Service Account with IAM roles
# - .env file with connection details
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

**Embeddings (Pluggable Providers)**

**Current:** Vertex AI text-embedding-005 (768 dimensions)

**Why text-embedding-005?** Specialized model for English and code tasks with excellent performance. Using 768 dimensions provides good quality while keeping storage costs reasonable.

**Alternatives:**
- gemini-embedding-001 (up to 3072 dimensions) - latest unified model, superior quality, supports multilingual
- text-embedding-004 (768 dimensions) - older stable model
- sentence-transformers (local, 384 dimensions) - 100% portable, no API costs

**To upgrade to gemini-embedding-001:**
- Same 768 dimensions: drop-in replacement, no schema changes needed
- Higher dimensions (1024-3072): better quality, requires recreating vector tables and re-embedding all documents

**To switch providers:**
1. Update embedding model in `document_processor.py` and `main.py`
2. Update vector dimension in `database.py` schema
3. **Regenerate all embeddings** (different dimensions require new vectors)
4. Fetch extracted text from GCS to avoid re-processing files
5. Update embeddings in PostgreSQL

```python
# Change in src/main.py and src/document_processor.py
self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
self.embedding_dimension = 1408

# Update database.py
CREATE TABLE document_chunks (
    embedding VECTOR(1408) NOT NULL,  # Match new dimension
    ...
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
# Unit tests
pytest tests/unit/ -v

# E2E tests (requires running server)
pytest tests/e2e/ -v

# Integration tests
python scripts/test_api.py
```

## Chunking Strategy

### Why 2000 chars?

Our chunking strategy balances **RAG quality** vs **API efficiency**:

- **chunk_size: 2000 chars** (~500 tokens)
  - Too small (<500 chars): loses context, too many API calls
  - Too large (>3000 chars): reduces search precision, noisy results
  - Sweet spot: 1500-2000 chars for semantic coherence

- **chunk_overlap: 200 chars**
  - Prevents information loss at boundaries
  - Improves retrieval when answer spans multiple chunks

### Retry Logic (Safety Net)

While `text-embedding-005` supports up to **20,000 tokens** (our chunks are ~500), we include retry logic as defense-in-depth:

1. **Try:** Send chunk to Vertex AI embedding API
2. **Catch:** If `400 error` + `"token"` in message (rare)
3. **Split:** Divide at semantic boundary (paragraphs → sentences → words)
4. **Recurse:** Process sub-chunks separately (max depth: 3)
5. **Result:** Multiple (text, embedding) pairs instead of averaging

**Key invariant:** `#chunks = #embeddings` (always synchronized between GCS and PostgreSQL)

### Performance Impact

- **bug_too_many.txt** (26KB): 13 chunks (was 58 with old 500-char chunks)
- **4.5x fewer API calls** with better context quality
- Retry never triggers in practice (2000 chars << 20K token limit)

## Project Structure

```
rag-lab/
├── src/
│   ├── main.py                    # FastAPI app (upload + query + deduplication)
│   ├── database.py                # PostgreSQL + pgvector (embeddings + metadata)
│   ├── storage.py                 # Cloud Storage (documents + text + chunks)
│   ├── document_processor.py      # PDF/TXT → chunks → embeddings
│   └── __init__.py
├── deployment/
│   ├── setup_infrastructure.py    # GCP resource provisioning (Python)
│   ├── deploy_cloudrun.py         # Cloud Run deployment (Python)
│   ├── local_run.py               # Local dev with Cloud SQL Proxy (Python)
│   ├── teardown.py                # Infrastructure cleanup (Python)
│   ├── .env.deploy.example        # Configuration template
│   └── .gitignore                 # Ignore secrets
├── tests/
│   └── fixtures/
│       └── documents/             # 4 test documents (22.6KB)
│           ├── rag_architecture_guide.txt
│           ├── gcp_services_overview.txt
│           ├── fastapi_best_practices.txt
│           ├── pgvector_complete_guide.txt
│           └── README.md          # Test scenarios
├── Dockerfile                     # Multi-stage production build
├── .gcloudignore                  # Cloud Run deployment filter
├── docker-compose.yaml            # Local development stack
├── requirements.txt               # Python dependencies
└── README.md                      # This file
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

## Features

✅ **Implemented:**
- Document upload (PDF, TXT)
- SHA256 deduplication (prevents duplicate processing)
- Vector similarity search
- Hybrid storage (PostgreSQL + GCS)
- Local development with Cloud SQL Proxy
- Automated GCP infrastructure setup
- Cloud Run deployment scripts
- Test fixtures for integration testing
- Vertex AI embeddings: text-embedding-005 (768 dimensions)

## Roadmap

- [ ] Document listing endpoint: `GET /v1/documents` (list all with metadata)
- [ ] Document download endpoint: `GET /v1/documents/{uuid}/download` (GCS signed URL)
- [ ] Document deletion endpoint: `DELETE /v1/documents/{uuid}` (GCS + DB cleanup)
- [ ] Add Gemini integration for answer generation
- [ ] Implement authentication (API keys, OAuth)
- [ ] Add rate limiting (slowapi)
- [ ] Enhanced monitoring and structured logging
- [ ] Add support for DOCX, HTML, Markdown
- [ ] Create Kubernetes manifests for GKE
- [ ] Comprehensive test suite (pytest)
- [ ] Search result reranking
- [ ] Redis caching for hot chunks (reduce GCS calls)
- [ ] Metadata filtering in queries (by filename, date, type)

## License

MIT

## Contributing

PRs welcome! This is a learning project exploring production RAG architectures.
