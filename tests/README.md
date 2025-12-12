# RAG Lab Test Suite

Comprehensive test suite for RAG Lab API covering unit, integration, and end-to-end testing.

## Test Structure

```
tests/
├── unit/                    # Fast, isolated tests with mocks
├── integration/             # Real API calls to external services
├── e2e/                     # Full workflow through HTTP API
└── fixtures/                # Test data (PDFs, text files, etc.)
```

## Test Types

### Unit Tests (`tests/unit/`)

**Purpose:** Test individual components in isolation

**Characteristics:**
- ✅ Use mocks for external dependencies (genai_client, database, GCS)
- ✅ Fast execution (< 1 second per test)
- ✅ No network/credentials required
- ✅ Run on every code change

**Coverage:**
- Text extraction (PDF, JSON, XML, CSV, Markdown, etc.)
- YAML conversion for structured data (JSON→YAML, XML→YAML)
- Chunking logic (size, overlap, metadata)
- File format validation
- Utility functions (hashing, etc.)

**Run:**
```bash
pytest tests/unit/ -v
```

### Integration Tests (`tests/integration/`)

**Purpose:** Test real integration with external services

**Characteristics:**
- ✅ Use REAL Vertex AI API (no mocks!)
- ✅ Use REAL database connections
- ✅ Slower execution (seconds to minutes)
- ✅ Require GCP credentials and network access

**Coverage:**
- Real embedding generation with Vertex AI
- Document upload → embedding → storage pipeline
- Chunking integrity (no data loss)
- Large file processing (performance, timeouts)

**Requirements:**
- `GCP_PROJECT_ID` environment variable
- GCP credentials configured (`gcloud auth` or service account)
- Vertex AI API enabled
- Running server for some tests (chunking_integrity)

**Run:**
```bash
# All integration tests
pytest tests/integration/ -v

# Specific test file
pytest tests/integration/test_large_txt_processing.py -v
```

### E2E Tests (`tests/e2e/`)

**Purpose:** Test complete user workflows through HTTP API

**Characteristics:**
- ✅ Full stack: FastAPI server + Vertex AI + Database + GCS
- ✅ HTTP requests (not direct Python calls)
- ✅ Slowest execution (can take minutes)
- ✅ Require running server + all credentials

**Coverage:**
- Document upload (TXT, PDF, JSON, Markdown)
- Semantic search
- Document download
- Document deletion
- Multi-format support

**Requirements:**
- Server running on `http://localhost:8080`
- All GCP services configured
- Test documents not left in system (auto-cleanup)

**Run:**
```bash
# Start server first
cd /Users/Rostislav_Dublin/src/drs/ai/rag-lab
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload &

# Run E2E tests
pytest tests/e2e/ -v -s

# With no cleanup (leave test docs for inspection)
pytest tests/e2e/ -v -s --no-cleanup
```

## Running All Tests

```bash
# All tests (unit + integration + e2e)
pytest tests/ -v

# Only fast tests (unit)
pytest tests/unit/ -v

# Only tests requiring credentials (integration + e2e)
pytest tests/integration/ tests/e2e/ -v
```

## Test Philosophy

### What to Mock

**Unit Tests:**
- ✅ Mock `genai_client` (no real Vertex AI calls)
- ✅ Mock database connections
- ✅ Mock GCS storage
- ✅ Mock external HTTP APIs

**Integration Tests:**
- ❌ NO mocks for external services
- ✅ Real Vertex AI embeddings
- ✅ Real database queries
- ✅ Real GCS uploads

**E2E Tests:**
- ❌ NO mocks at all
- ✅ Full production-like environment

### When Tests Should Fail

**Unit tests fail when:**
- Code logic is broken
- API contracts change
- Refactoring introduces bugs

**Integration tests fail when:**
- Vertex AI quota exceeded
- Network issues
- Credentials expired
- Database schema changed
- GCS bucket not accessible

**E2E tests fail when:**
- Any part of the stack is broken
- Server not running
- Any external service unavailable

## Current Test Coverage

- **44 total tests**
  - 30 unit tests (format support, chunking, extraction)
  - 5 integration tests (real Vertex AI, large files)
  - 9 e2e tests (full HTTP workflows)

## Key Fixtures

### Unit Tests
- `processor` - DocumentProcessor with mock genai_client
- `fixtures_dir` - Path to test documents

### Integration Tests (conftest.py)
- `genai_client` - **Real** Vertex AI client (session-scoped)
- Auto-skips if `GCP_PROJECT_ID` not set

### E2E Tests
- `test_documents` - Paths to test files + their hashes
- `cleanup_test_documents` - Auto-cleanup after tests (unless `--no-cleanup`)

## Debugging Tests

```bash
# Verbose output with print statements
pytest tests/unit/test_text_formats.py -v -s

# Stop on first failure
pytest tests/unit/ -x

# Run specific test
pytest tests/unit/test_text_formats.py::test_json_extraction -v

# Show local variables on failure
pytest tests/integration/ -v --tb=long
```

## CI/CD Considerations

**Fast CI (every commit):**
```bash
pytest tests/unit/ -v
```

**Full CI (before merge):**
```bash
# Requires GCP credentials in CI environment
pytest tests/unit/ tests/integration/ -v
```

**Nightly/Release:**
```bash
# Full E2E with running server
pytest tests/ -v
```
