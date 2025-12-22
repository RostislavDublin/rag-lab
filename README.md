# RAG Lab - RAG-as-a-Service

Production-ready Retrieval Augmented Generation (RAG) system with hybrid storage, multi-format support, LLM reranking, and comprehensive authentication.

## 📖 How to Use This Documentation

**This README is a navigation hub, not a comprehensive guide.**

### For Humans (First-time users):
1. **Start here** to understand what the project does
2. **Follow topic links** to `docs/` for detailed technical information
3. **Come back to README** when you need to find a specific guide

### For AI Assistants (including Copilot):
1. **ALWAYS read README first** when starting work in this project
2. **Then read ALL linked documentation** for your task:
   - Setting up locally? → Read [Development Guide](docs/development.md)
   - Deploying to Cloud Run? → Read [Deployment Guide](docs/deployment.md)
   - Working with API? → Read [API Reference](docs/api.md)
   - Implementing auth? → Read [Authentication](docs/authentication.md)
   - Writing tests? → Read [Testing Guide](docs/testing.md)
3. **During work:** Reference the relevant topic document, not README

**Why this matters:**
- README was restructured from 1480 lines to focused topic files
- Each `docs/*.md` file contains COMPLETE information for its domain
- Reading only README without following links = missing critical context
- AI: You MUST read the linked docs to get full context

---

## Key Features

- **Hybrid Search**: Vector similarity + BM25 keyword + RRF fusion (Phase 3 complete, v0.3.0)
- **Hybrid Storage**: PostgreSQL (embeddings + metadata) + GCS (documents, 8.5x cheaper)
- **LLM Reranking**: Gemini-powered async batch reranking with reasoning explanations
- **Multi-format**: 17 formats (PDF→MD, HTML→MD, JSON→YAML, XML→YAML, code, logs)
- **UUID-based**: Globally unique, immutable document identifiers
- **Deduplication**: SHA256 content hashing prevents duplicate uploads
- **JWT/JWKS Auth**: Vendor-independent (Google, Azure AD, Auth0, Okta)
- **Service Delegation**: `X-End-User-ID` header for service-to-service flows
- **Cost-effective**: Cloud Run auto-scales to zero ($0-5/month)
- **Comprehensive Testing**: 69 tests (38 e2e, 23 integration, 8 unit - all passing)

## Documentation

**📚 Complete technical guides (read these for details!):**

- **[Development Guide](docs/development.md)** - Local setup, `.env.local` vs `.env` vs `.env.deploy`, logging
- **[Dependencies Architecture](docs/dependencies.md)** - Modular dependencies, provider selection, build optimization
- **[Deployment Guide](docs/deployment.md)** - Cloud Run deployment, infrastructure, cost estimates
- **[API Reference](docs/api.md)** - REST API endpoints, MongoDB filters, request/response examples
- **[Authentication](docs/authentication.md)** - JWT/JWKS, service delegation, multi-tenancy
- **[Testing Guide](docs/testing.md)** - Running tests, writing tests, CI/CD, markers
- **[File Validation](docs/file-validation.md)** - 3-tier validation, magic bytes, security
- **[Reranking Deep Dive](docs/reranking.md)** - LLM reranking implementation, performance
- **[E2E Testing](tests/e2e/README.md)** - End-to-end workflow, iterative development

## Architecture

High-level system architecture (see [API Reference](docs/api.md) for details):

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
    │  Embeddings  │  │  PostgreSQL  │  │  Storage     │  │  Reranking   │
    │  (768-dim)   │  │  + pgvector  │  │  (GCS)       │  │  (optional)  │
    └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

**Key Design Decisions:**
- **Hybrid Storage:** PostgreSQL (embeddings + metadata) + GCS (documents/chunks) = 8.5x cheaper
- **UUID-based:** Immutable, globally unique document identifiers
- **Deduplication:** SHA256 content hashing prevents duplicate processing
- **No Egress Costs:** Cloud Run + GCS in same region = $0 data transfer

**For detailed architecture:** [Development Guide](docs/development.md) | [Deployment Guide](docs/deployment.md)

## Quick Start

### Local Development

```bash
# 1. Clone and setup
git clone <repository-url> && cd rag-lab
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies (base + optional providers)
pip install -r requirements.txt

# OR install only Vertex AI providers (no torch/sentence-transformers):
# pip install -r requirements-base.txt

# 2. Configure environment
cp .env.local.example .env.local
# Edit .env.local with your settings (see docs/development.md for details)

# 3. Start server with hot reload
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

### Production Deployment (Cloud Run with CI/CD)

```bash
# 1. Setup infrastructure (one-time)
cd deployment
cp .env.deploy.example .env.deploy
# Edit: GCP_PROJECT_ID, GCP_REGION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME
./setup-infrastructure.sh
./setup-cloudbuild-trigger.sh  # Connects GitHub, creates trigger

# 2. Configure and upload secrets
cd ..
cp .env.example .env
# Edit .env with production settings
cd deployment && ./upload-secrets.sh

# 3. Create deploy branch and push
git checkout -b deploy/production
git push origin deploy/production  # Auto-deploys via Cloud Build!

# See deployment/CLOUDBUILD_SETUP.md for complete guide
```

**Server runs at:** http://localhost:8080 | **Swagger UI:** http://localhost:8080/docs

**⚠️ Important:** See [Development Guide](docs/development.md) for:
- `.env.local` vs `.env` vs `.env.deploy` (different purposes!)
- Cloud SQL Proxy setup
- Database connection strings
- Authentication configuration

### Cloud Run Deployment

```bash
cd deployment

# 1. Setup infrastructure (one-time)
cp .env.deploy.example .env.deploy
# Edit .env.deploy with GCP project/region
./setup-infrastructure.sh  # Creates Cloud SQL, GCS, Service Account

# 2. Configure application
cd ..
cp .env.example .env
# Edit .env with all app settings (embeddings, reranking, auth, secrets)

# 3. Deploy
cd deployment
./deploy-cloudrun.sh  # Uploads .env to Secret Manager, builds & deploys
```

**⚠️ Important:** See [Deployment Guide](docs/deployment.md) for:
- **Secret Manager setup** (configuration mounted as volume, not in image)
- Infrastructure resource planning
- Cost estimates ($0-12/month breakdown)
- Platform portability strategy
- Troubleshooting common issues

## API Examples

**Quick examples** (see [API Reference](docs/api.md) for complete documentation):

```bash
# Upload document with metadata
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "files=@document.pdf" \
  -F 'metadata={"category":"technical","priority":"high"}'

# Hybrid search with reranking
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does authentication work?",
    "top_k": 10,
    "use_hybrid": true,
    "filters": {"category": {"$eq": "technical"}},
    "rerank": true,
    "rerank_top_k": 5
  }'
```

**For full API details:** [API Reference](docs/api.md)

## Testing

```bash
# Run all tests
pytest -v

# Run by category
pytest tests/e2e/ -v           # 38 end-to-end tests
pytest tests/integration/ -v   # 23 integration tests  
pytest tests/unit/ -v          # 8 unit tests

# Run specific test markers
pytest -m reranking -v         # Reranking tests only
pytest -m "not cleanup" -v     # Skip cleanup (iterative dev)
```

**For testing details:** [Testing Guide](docs/testing.md) | [E2E Testing](tests/e2e/README.md)

## Project Structure

```
rag-lab/
├── src/                           # Application code
│   ├── main.py                   # FastAPI app + endpoints
│   ├── database.py               # PostgreSQL + pgvector
│   ├── storage.py                # GCS operations
│   ├── auth/                     # JWT/JWKS validation
│   ├── extraction/               # PDF, HTML, JSON, XML, code extractors
│   ├── chunking/                 # Semantic chunking
│   ├── embedding/                # Vertex AI embeddings
│   ├── reranking/                # Gemini LLM reranking
│   └── validation/               # 3-tier file validation
├── tests/                         # 69 tests (38 e2e, 23 integration, 8 unit)
│   ├── unit/                     # Isolated function tests
│   ├── integration/              # Real Vertex AI tests
│   └── e2e/                      # Full HTTP workflow tests
├── deployment/                    # Cloud Run deployment scripts
├── docs/                          # Detailed technical guides
├── .env.local                     # Local development config (gitignored)
├── .env                           # Cloud Run production config (gitignored)
└── deployment/.env.deploy         # Infrastructure config (gitignored)
```

**For complete structure:** See respective documentation in `docs/`

## Roadmap

Current version: **0.3.0** - Hybrid Search Complete

See [ROADMAP.md](ROADMAP.md) for:
- Detailed feature planning
- Implementation timeline
- Priority levels (P1-P4)
- Cost estimates

**Next priorities:**
1. Schema Migrations (P1, 12-16h)
2. Parent Document Retrieval (P2, 10h)
3. Async Processing (P3, 10h)

## Contributing

PRs welcome! This is a learning project exploring production RAG architectures.

## License

MIT
