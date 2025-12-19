# RAG Lab - Copilot Instructions

## Project Overview

**RAG Lab** is an experimental workspace for exploring Retrieval Augmented Generation (RAG) technologies, primarily using Google Cloud AI services.

## Purpose

- Learning and experimenting with RAG architectures
- Understanding Google Vertex AI RAG capabilities
- Exploring multimodal RAG implementations
- Testing vector database options
- Building production-ready RAG patterns

## Tech Stack

- **Primary**: Google Vertex AI, Gemini, Text/Multimodal Embeddings
- **Vector Stores**: Vertex AI Vector Search, PostgreSQL + pgvector, AlloyDB
- **Language**: Python 3.10+
- **API Framework**: FastAPI + uvicorn
- **Reference**: Google's generative-ai repository for authoritative examples

## Project Status

Active learning project - experimentation and prototyping phase.

## 📚 GETTING STARTED WITH PROJECT DOCUMENTATION

**When starting work in this project for the first time or after a long break:**

1. **ALWAYS read the main README.md first** (`/Users/Rostislav_Dublin/src/drs/ai/rag-lab/README.md`)
   - Provides project overview, architecture, features, quick start
   - Contains links to ALL topic-specific documentation

2. **Read ALL topic documentation from README links:**
   - `docs/development.md` - Local setup, configuration, environment variables, logging
   - `docs/deployment.md` - Cloud Run deployment, infrastructure, cost estimates
   - `docs/api.md` - REST API reference, MongoDB filters, all endpoints
   - `docs/authentication.md` - JWT/JWKS, service delegation, multi-tenancy
   - `docs/testing.md` - Test guide, workflow, fixtures, CI/CD
   - `docs/file-validation.md` - 3-tier validation, magic bytes, security
   - `docs/reranking.md` - LLM reranking implementation, performance optimization
   - `tests/e2e/README.md` - End-to-end test workflow, markers, iterative development

3. **During active work: focus on relevant topic document**
   - Working on API changes? → Reference `docs/api.md`
   - Setting up local dev? → Reference `docs/development.md`
   - Writing tests? → Reference `docs/testing.md`
   - Implementing auth? → Reference `docs/authentication.md`
   - Deploying to Cloud Run? → Reference `docs/deployment.md`
   - Adding file validation? → Reference `docs/file-validation.md`
   - Optimizing reranking? → Reference `docs/reranking.md`

**Why this matters:**
- Documentation is split into focused topic documents (README was restructured from 1480 lines to 8 focused files)
- Each document contains complete, detailed information for its domain
- Main README is now a navigation hub, not a comprehensive guide
- Reading only README without following links = missing critical context

## 🚨 LOCAL DEVELOPMENT - ABSOLUTE IRON RULES 🚨

**READ THIS BEFORE EVERY SERVER START! NO EXCEPTIONS!**

### CRITICAL: PYTEST E2E TEST EXECUTION

**NEVER attempt to run a single test method from `tests/e2e/test_full_rag_workflow.py`**

- E2E tests are **DEPENDENT** - they run in sequence (test_01, test_02, test_03, etc.)
- Each test depends on data/state from previous tests
- Running one test in isolation will ALWAYS FAIL
- User has reminded about this MULTIPLE times - DO NOT FORGET

**Correct ways to run E2E tests:**
```bash
# Run ALL E2E tests (recommended)
pytest tests/e2e/test_full_rag_workflow.py -v

# Run entire test suite
pytest tests/ -v

# Run specific test file (if independent tests)
pytest tests/unit/test_filter_parser.py::test_specific_function -v
```

**WRONG - NEVER DO THIS:**
```bash
# This will FAIL because test depends on previous tests
pytest tests/e2e/test_full_rag_workflow.py::test_04a_metadata_filter_single_user -v
```

### PREREQUISITES (CHECK FIRST!):

1. **`.env.local` MUST EXIST** in `/Users/Rostislav_Dublin/src/drs/ai/rag-lab/`
   - Contains DATABASE_URL, GCP_PROJECT_ID, GCS_BUCKET_NAME, etc.
   - If missing: copy from `.env.local.example` and fill in real values
   - Server will FAIL without this file!

2. **`.venv` MUST EXIST** in `/Users/Rostislav_Dublin/src/drs/ai/rag-lab/`
   - Virtual environment with all dependencies installed
   - If missing: run `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

### THE ONLY CORRECT WAY TO START SERVER:

```bash
# STEP 1: Go to rag-lab directory (ALWAYS!)
cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab

# STEP 2: Activate venv (MANDATORY!)
source .venv/bin/activate

# STEP 3: Start uvicorn (with --reload!)
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

### 🔴 CRITICAL - NEVER FORGET THESE STEPS:

**STEP 0 (PREREQUISITE)** - `.env.local` MUST EXIST
   - File location: `/Users/Rostislav_Dublin/src/drs/ai/rag-lab/.env.local`
   - Contains: DATABASE_URL, GCP_PROJECT_ID, GCS_BUCKET_NAME
   - If server crashes on startup with DB error: check .env.local!
   - FastAPI loads .env.local automatically (higher priority than .env)

1. **STEP 1 IS MANDATORY** - `cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab`
   - Without this: .venv won't be found
   - Current directory MUST be `/Users/Rostislav_Dublin/src/drs/ai/rag-lab`
   - Check with `pwd` if unsure

2. **STEP 2 IS MANDATORY** - `source .venv/bin/activate`
   - Without this: uvicorn command won't be found
   - You MUST see `(.venv)` in terminal prompt after activation
   - If activation fails: venv doesn't exist or wrong directory

3. **STEP 3 IS MANDATORY** - `uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload`
   - NEVER use `python3 -m uvicorn` (won't work without venv active)
   - NEVER use Docker (that's for deployment, not local dev)
   - ALWAYS include `--reload` (auto-reload on code changes)

### ✅ HOW TO START SERVER (AI ASSISTANT CHECKLIST):

When user asks to start/restart server:

- [ ] Step 1: `cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab`
- [ ] Step 2: `source .venv/bin/activate`  
- [ ] Step 3: `uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload`
- [ ] Run as background process (isBackground=true)

**ALL THREE STEPS IN ONE COMMAND:**

```bash
cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab && source .venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

### 🟢 HOT RELOAD - NEVER RESTART SERVER!

- Code changes apply **automatically** (watch terminal for "Detected change, reloading...")
- **NEVER kill/restart** server after code edits
- Only restart if server crashed or you changed dependencies

### 🔴 TO STOP SERVER:

- `Ctrl+C` in terminal
- If stuck: `lsof -ti:8080 | xargs kill`

### 🟢 AFTER SERVER STARTS:

- API: http://localhost:8080
- Swagger UI: http://localhost:8080/docs  
- Health check: `curl http://localhost:8080/health`

## Important Notes

- **Service Account Keys**: Never commit `service-account-key.json` or similar credential files
- **Data Files**: Large datasets and model files should be in `.gitignore`
- **Experiments**: Ad-hoc experiments belong in `experiments/` directory
- **Reusable Code**: Production-quality code goes in `src/`

## Google AI SDK Usage - CRITICAL

**ALWAYS use the NEW Google Gen AI SDK (not deprecated Vertex AI modules):**

- ✅ **USE:** `from google import genai`
- ✅ **USE:** `client = genai.Client(vertexai=True, project=..., location=...)`
- ✅ **USE:** `client.models.embed_content(model="text-embedding-005", contents=...)`
- ✅ **USE:** `client.models.generate_content(model="gemini-2.5-flash", contents=...)`

- ❌ **NEVER USE:** `from vertexai.language_models import TextEmbeddingModel`
- ❌ **NEVER USE:** `from vertexai.generative_models import GenerativeModel`
- ❌ **NEVER USE:** `TextEmbeddingModel.from_pretrained(...)`
- ❌ **NEVER USE:** `model.get_embeddings([...])`

**Why:**
- `vertexai.language_models`, `vertexai.generative_models`, `vertexai.vision_models` are **deprecated** as of June 24, 2025
- They will be **removed** on June 24, 2026
- Migration guide: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk

**Exceptions:**
- RAG API still uses `from vertexai import rag` (stable, not deprecated)
- `vertexai.init()` still needed for initialization

**Install:**
```bash
pip install google-genai>=0.3.0
```

## Git Workflow

Follow the same git workflow as other projects:
- DO NOT commit/push without explicit user authorization
- User must say "commit", "push", "c&p", or equivalent
- Show git status and wait for confirmation

## BigQuery Billing Analytics

**Dataset configured:** `myai-475419.billing_export` (US multi-region)
**Export started:** December 18, 2025
**Export type:** Detailed usage cost (SKU-level breakdown)

**Purpose:** Track and analyze Google Cloud costs, especially:
- Vertex AI API costs (Gemini generation, embeddings)
- Detailed SKU breakdown (flash vs flash-lite, input/output tokens)
- Identify cost drivers for reranking, extraction, and RAG operations

**When user asks for billing details or cost breakdown:**
1. Query `myai-475419.billing_export.gcp_billing_export_v1_*` (standard export)
2. Query `myai-475419.billing_export.gcp_billing_export_resource_v1_*` (detailed export for SKU-level)
3. Filter by date range user specifies (default: last 7 days)
4. Group by service, SKU, and show total costs
5. Identify Vertex AI API costs separately

**Example query template:**
```sql
SELECT
  service.description AS service,
  sku.description AS sku_name,
  COUNT(*) AS usage_count,
  SUM(usage.amount) AS total_usage,
  SUM(cost) AS total_cost
FROM `myai-475419.billing_export.gcp_billing_export_resource_v1_*`
WHERE DATE(_PARTITIONTIME) BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
  AND cost > 0
GROUP BY service, sku_name
ORDER BY total_cost DESC
LIMIT 20
```

**Cost context:**
- Storage: First 10 GiB/month FREE (billing data ~100-500 MB → $0)
- Queries: First 1 TiB/month FREE (typical usage well under limit → $0)
- **Total billing export cost: $0/month**

## Learning Resources

- Primary: `/Users/Rostislav_Dublin/src/drs/ai/generative-ai/` (Google's official examples)
- Secondary: `/Users/Rostislav_Dublin/src/drs/ai/capstone/` (practical RAG Corpus patterns)
