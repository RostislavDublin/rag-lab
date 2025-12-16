# RAG Lab - RAG-as-a-Service

Production-ready Retrieval Augmented Generation (RAG) system with:
- **Hybrid storage**: PostgreSQL for embeddings, GCS for documents (8.5x cheaper)
- **LLM reranking**: Gemini-powered async batch reranking with reasoning (7-8s for 20 docs)
- **UUID-based**: Globally unique, immutable document identifiers
- **Deduplication**: SHA256 file hashing prevents duplicate uploads
- **Multi-format support**: 17 formats (PDF, TXT, MD, JSON, XML, CSV, YAML, code files, logs)
- **Structured data**: YAML conversion for JSON/XML preserves semantic information
- **Vendor-independent auth**: JWT/JWKS supports Google, Azure AD, Auth0, Okta
- **Service delegation**: `X-End-User-ID` header for service-to-service flows
- **Multi-cloud portable**: PostgreSQL + pgvector + GCS works everywhere
- **Cost-effective**: Cloud Run auto-scales to zero ($0-5/month)
- **Local development**: Fast iteration with Cloud SQL Proxy and hot reload
- **Comprehensive testing**: 162 tests (37 e2e, 13 integration, 112 unit including auth/filter parser/reranking/file validation)

## Documentation

- **[Development Guide](docs/development.md)** - Local setup, configuration, environment variables, logging
- **[Deployment Guide](docs/deployment.md)** - Cloud Run deployment, infrastructure setup, cost estimates
- **[API Reference](docs/api.md)** - REST API endpoints, request/response examples, MongoDB filters
- **[Authentication](docs/authentication.md)** - JWT/JWKS, service delegation, protected metadata, multi-tenancy
- **[Testing Guide](docs/testing.md)** - Running tests, writing tests, CI/CD integration, performance testing
- **[File Validation](docs/file-validation.md)** - 3-tier validation, magic bytes, security considerations
- **[Reranking Deep Dive](docs/reranking.md)** - LLM reranking implementation, performance optimization
- **[E2E Testing](tests/e2e/README.md)** - End-to-end test workflow, markers, iterative development

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
uploaded_by (TEXT)        │       CASCADE DELETE ◄──────┘
uploaded_at (TIMESTAMP)   │
uploaded_via (TEXT)       │
metadata (JSONB)          │  ← User-defined fields only
chunk_count               │     (department, tags, priority, etc.)
                          │     System fields are columns
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

## Quick Start

### Prerequisites

1. **Python 3.12+**
2. **PostgreSQL 15+ with pgvector**
3. **Google Cloud Project** with Vertex AI enabled
4. **GCP credentials** with required permissions

### Local Development

```bash
# 1. Clone repository
git clone <repository-url>
cd rag-lab

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env.local file
cp .env.local.example .env.local
# Edit .env.local with your configuration
# See docs/development.md for details

# 5. Start server
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# Server runs at http://localhost:8080
# Swagger UI at http://localhost:8080/docs
```

**One-liner:**
```bash
cd rag-lab && source .venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

For detailed setup options (Docker Compose, Cloud SQL Proxy, environment variables), see **[Development Guide](docs/development.md)**.

### Cloud Run Deployment

```bash
# 1. Configure deployment
cd deployment
cp .env.deploy.example .env.deploy
# Edit .env.deploy with your GCP settings

# 2. Setup infrastructure (one-time)
python setup_infrastructure.py

# 3. Deploy to Cloud Run
python deploy_cloudrun.py

# 4. Test deployment
SERVICE_URL=$(gcloud run services describe rag-api --region us-central1 --format 'value(status.url)')
curl $SERVICE_URL/health
```

For detailed deployment instructions, cost estimates, and troubleshooting, see **[Deployment Guide](docs/deployment.md)**.

## API Examples

### Upload Document

```bash
curl -X POST http://localhost:8080/upload \
  -F "files=@document.pdf" \
  -F 'metadata={"category":"technical","priority":"high"}'
```

### Hybrid Search with Reranking

```bash
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does authentication work?",
    "top_k": 10,
    "metadata_filter": {"category": {"$eq": "technical"}},
    "rerank": true,
    "rerank_top_k": 5
  }'
```

For complete API documentation (all endpoints, metadata filtering, error handling), see **[API Reference](docs/api.md)**.

## Testing

```bash
# Run all tests (162 total)
pytest -v

# Run by category
pytest tests/e2e/ -v           # 37 e2e tests
pytest tests/integration/ -v   # 13 integration tests
pytest tests/unit/ -v          # 112 unit tests

# Run by marker
pytest -m reranking -v         # LLM reranking tests
pytest -m "not cleanup" -v     # Skip cleanup (iterative development)

# Coverage report
pytest --cov=src --cov-report=html
```

For detailed testing guide (workflow, fixtures, writing tests, CI/CD), see **[Testing Guide](docs/testing.md)** and **[E2E Testing](tests/e2e/README.md)**.

## Project Structure

```
rag-lab/
├── src/
│   ├── main.py                    # FastAPI app, upload endpoint
│   ├── database.py                # PostgreSQL + pgvector
│   ├── storage.py                 # GCS operations
│   ├── logging_config.py          # Rotating logs with timestamps
│   ├── auth/
│   │   ├── jwt_auth.py            # JWT/JWKS validation
│   │   └── metadata_protection.py # Protected metadata fields
│   ├── extraction/
│   │   ├── pdf_extractor.py       # PDF → Markdown (pypdfium2, PyPDF2)
│   │   ├── html_extractor.py      # HTML → Markdown (beautifulsoup4)
│   │   ├── text_extractor.py      # TXT/MD direct read
│   │   ├── structured_extractor.py # JSON/XML → YAML
│   │   └── code_extractor.py      # Python/JS/Java/etc extraction
│   ├── chunking/
│   │   └── chunker.py             # Semantic chunking
│   ├── embedding/
│   │   └── embedder.py            # Vertex AI text-embedding-005
│   ├── reranking/
│   │   └── gemini.py              # Async batch reranking (10 parallel, batch_size=2)
│   └── validation/
│       └── file_validator.py      # 3-tier validation (extension, magic bytes, extraction)
├── tests/
│   ├── unit/                      # 112 tests (isolated functions)
│   │   ├── test_filter_parser.py  # 65 tests (MongoDB operators)
│   │   ├── test_reranking.py      # 6 tests (keyword trap)
│   │   └── test_file_validator.py # 17 tests (3-tier validation)
│   ├── integration/               # 13 tests (real Vertex AI)
│   └── e2e/                       # 37 tests (full HTTP workflow)
│       ├── test_full_rag_workflow.py
│       └── README.md              # E2E testing guide
├── deployment/
│   ├── setup_infrastructure.py    # GCP infrastructure automation
│   ├── deploy_cloudrun.py         # Cloud Run deployment
│   └── teardown.py                # Cleanup resources
├── docs/
│   ├── development.md             # Local setup, configuration, logging
│   ├── deployment.md              # Cloud Run deployment, cost estimates
│   ├── api.md                     # REST API reference
│   ├── authentication.md          # JWT/JWKS, multi-tenancy
│   ├── testing.md                 # Testing guide, CI/CD
│   ├── file-validation.md         # 3-tier validation, magic bytes
│   └── reranking.md               # LLM reranking deep dive
├── pyproject.toml                 # pytest config, markers
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yaml            # Local development stack
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Features

✅ **Implemented:**
- **Multi-format upload:** 17 formats (PDF→MD, HTML→MD, TXT, MD, JSON→YAML, XML→YAML, CSV, YAML, code, logs)
- **Smart document processing:** 
  - PDF/HTML → Markdown (preserves structure: headings, tables, lists)
  - JSON/XML → YAML (minimizes syntax noise, maintains semantics)
  - Text formats → direct UTF-8 extraction
- **File validation:** 3-tier strategy (strict/structured/lenient) with magic bytes detection
- **SHA256 deduplication:** Content-based duplicate detection
- **LLM reranking:** Gemini 2.5-flash async batch reranking (2 docs/batch, 10 parallel)
  - Reasoning explanation for each document
  - 7-8s for 20 documents
  - Deterministic keyword trap test validates semantic understanding
- **Vector similarity search:** PostgreSQL + pgvector (768-dim embeddings)
- **Hybrid storage:** PostgreSQL (metadata + vectors) + GCS (files + text)
- **CRUD operations:** Upload, list, query, delete (by ID or hash)
- **Google Gen AI SDK:** text-embedding-005 embeddings (768 dimensions)
- **JWT/JWKS authentication:** Vendor-independent OAuth2 (Google, Azure AD, Auth0, Okta)
- **Metadata filtering:** MongoDB Query Language (12 operators: $and, $or, $not, etc.)
- **Rotating logs:** Timestamp-based sessions with automatic retention (10MB × 10 files)
- **Local development:** uvicorn hot reload + Cloud SQL Proxy
- **Automated deployment:** GCP infrastructure setup + Cloud Run
- **Comprehensive testing:** 162 tests (37 e2e, 13 integration, 112 unit)
- **Test fixtures:** 17 documents covering all supported formats + keyword trap scenarios

## Roadmap

- [x] ~~Document listing endpoint~~ - `GET /v1/documents` implemented
- [x] ~~Document deletion endpoint~~ - `DELETE /v1/documents/{id}` and `DELETE /v1/documents/by-hash/{hash}` implemented
- [x] ~~Implement authentication~~ - JWT/JWKS with OAuth2, vendor-independent
- [x] ~~Metadata filtering in queries~~ - MongoDB Query Language with 12 operators
- [x] ~~Search result reranking~~ - Gemini LLM async batch reranking with reasoning (7-8s for 20 docs)
- [x] ~~Enhanced structured logging~~ - Rotating log files with timestamp-based sessions
- [ ] Document download endpoint: `GET /v1/documents/{uuid}/download` (GCS signed URL)
- [ ] Add Gemini integration for answer generation
- [ ] Add rate limiting (slowapi)
- [ ] Add support for DOCX, PPTX, EPUB
- [ ] Create Kubernetes manifests for GKE
- [ ] Redis caching for hot chunks (reduce GCS calls)
- [ ] Hybrid search (vector + BM25 keyword search with RRF fusion)

## License

MIT

## Contributing

PRs welcome! This is a learning project exploring production RAG architectures.
