# Testing Guide

Complete guide to running and writing tests for RAG Lab.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── e2e/                     # End-to-end integration tests
│   ├── test_full_rag_workflow.py
│   └── README.md
├── integration/             # Integration tests (API + DB)
│   ├── test_api.py
│   ├── test_database.py
│   └── test_storage.py
├── unit/                    # Unit tests (isolated functions)
│   ├── test_chunking.py
│   ├── test_extraction.py
│   ├── test_reranking.py
│   └── test_validation.py
└── fixtures/                # Test data
    ├── documents/           # Sample PDFs, DOCX, TXT
    └── metadata/            # Sample metadata JSON
```

## Running Tests

### All Tests (162 total)

```bash
pytest -v
# 37 e2e + 13 integration + 112 unit
```

### By Category

```bash
# End-to-end tests only (37 tests)
pytest tests/e2e/ -v

# Integration tests only (13 tests)
pytest tests/integration/ -v

# Unit tests only (112 tests)
pytest tests/unit/ -v
```

### By Marker

```bash
# E2E workflow markers
pytest tests/e2e/ -m upload -v           # Document upload
pytest tests/e2e/ -m semantic_search -v  # Semantic search
pytest tests/e2e/ -m reranking -v        # LLM reranking
pytest tests/e2e/ -m metadata_filter -v  # Metadata filtering
pytest tests/e2e/ -m cleanup -v          # Cleanup tests

# Skip cleanup (iterative development)
pytest tests/e2e/ -m "not cleanup" -v

# Run specific test
pytest tests/e2e/test_full_rag_workflow.py::test_05h_query_with_reranking -v
```

### Coverage Report

```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html  # View detailed coverage
```

## E2E Test Workflow

E2E tests use **explicit cleanup tests** (not autouse fixtures):

```python
# tests/e2e/test_full_rag_workflow.py

@pytest.mark.cleanup
def test_00_cleanup_before():
    """Remove leftover documents from previous runs."""
    # Runs first (test_00)
    ...

@pytest.mark.upload
def test_01_upload_documents():
    """Upload test documents."""
    ...

@pytest.mark.reranking
def test_05h_query_with_reranking():
    """Test LLM reranking."""
    ...

@pytest.mark.cleanup
def test_99_cleanup_after():
    """Remove test documents."""
    # Runs last (test_99)
    ...
```

### Iterative Development Workflow

**Recommended for development:**

```bash
# 1. Upload documents ONCE
pytest tests/e2e/ -m upload -v

# 2. Run feature tests MANY TIMES (no re-upload)
pytest tests/e2e/ -m reranking -v
pytest tests/e2e/ -m reranking -v  # Again!
pytest tests/e2e/test_full_rag_workflow.py::test_05h_query_with_reranking -v

# 3. Clean up when done
pytest tests/e2e/ -m cleanup -v
```

**Benefits:**
- ✅ Upload once, test many times
- ✅ Fast iteration (no re-processing)
- ✅ Explicit control via markers

**Full suite (includes cleanup):**
```bash
pytest tests/e2e/test_full_rag_workflow.py -v
```

### Available Markers

Defined in `pytest.ini`:

```ini
[pytest]
markers =
    cleanup: Pre/post cleanup tests
    upload: Document upload tests
    semantic_search: Semantic search tests
    reranking: LLM reranking tests
    metadata_filter: Metadata filtering tests
    security: Security/auth tests
    list: Document listing tests
    download: Document download tests
    storage: Storage backend tests
```

## Test Fixtures

### Shared Fixtures (conftest.py)

```python
@pytest.fixture(scope="session")
def test_documents_dir():
    """Path to test documents."""
    return Path(__file__).parent / "fixtures" / "documents"

@pytest.fixture
def sample_pdf(test_documents_dir):
    """Sample PDF for testing."""
    return test_documents_dir / "sample.pdf"

@pytest.fixture
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)
```

### Using Fixtures

```python
def test_upload_pdf(client, sample_pdf):
    """Test uploading a PDF document."""
    with open(sample_pdf, "rb") as f:
        response = client.post(
            "/upload",
            files={"files": ("sample.pdf", f, "application/pdf")}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["uploaded_files"]) == 1
```

## Test Documents

### Standard Test Files

Located in `tests/fixtures/documents/`:

```
sample.pdf                    # Standard PDF (5 pages)
technical_doc.txt             # Technical content
red_riding_hood_story.txt     # Fairy tale (keyword trap test)
hybrid_search_technical.txt   # Technical doc with exact query match
```

### Keyword Trap Test

Tests that semantic search outperforms keyword matching:

```python
@pytest.mark.reranking
def test_05i_query_with_reranking_keyword_trap():
    """
    Keyword trap test:
    - Query: "hybrid search agent system"
    - Doc 1: Fairy tale with exact title match (low relevance)
    - Doc 2: Technical doc about agents (high relevance)
    - Test: Reranking should rank Doc 2 higher
    """
    response = client.post(
        "/search",
        json={
            "query": "hybrid search agent system",
            "top_k": 10,
            "rerank": True,
            "rerank_top_k": 5
        }
    )
    
    results = response.json()["results"]
    
    # Top result should be technical doc (high semantic relevance)
    assert "technical" in results[0]["filename"].lower()
    
    # Fairy tale should rank lower (despite keyword match)
    fairy_tale_rank = next(
        i for i, r in enumerate(results)
        if "red_riding_hood" in r["filename"]
    )
    assert fairy_tale_rank > 0  # Not first
```

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_chunking.py
from src.chunking import chunk_text

def test_chunk_text_basic():
    """Test basic text chunking."""
    text = "This is a test. " * 100  # Long text
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    
    assert len(chunks) > 1
    assert all(len(chunk) <= 500 for chunk in chunks)
    
    # Check overlap
    assert chunks[0][-50:] in chunks[1]
```

### Integration Test Example

```python
# tests/integration/test_database.py
import pytest
from src.database import Database

@pytest.fixture
async def db():
    """Database connection for testing."""
    db = Database(DATABASE_URL)
    await db.connect()
    yield db
    await db.disconnect()

async def test_insert_and_query(db):
    """Test inserting and querying chunks."""
    # Insert test chunk
    chunk_id = await db.insert_chunk(
        document_uuid="test-uuid",
        chunk_index=0,
        text="Test chunk",
        embedding=[0.1] * 768,
        metadata={"category": "test"}
    )
    
    # Query by vector similarity
    results = await db.query_similar(
        embedding=[0.1] * 768,
        top_k=1
    )
    
    assert len(results) == 1
    assert results[0]["text"] == "Test chunk"
```

### E2E Test Example

```python
# tests/e2e/test_full_rag_workflow.py
import pytest
from httpx import AsyncClient

@pytest.mark.upload
async def test_01_upload_documents(client):
    """Test document upload."""
    with open("tests/fixtures/documents/sample.pdf", "rb") as f:
        response = await client.post(
            "/upload",
            files={"files": ("sample.pdf", f, "application/pdf")},
            data={"metadata": '{"category":"test"}'}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["uploaded_files"][0]["total_chunks"] > 0
```

## Test Configuration

### Environment Variables

Tests use separate environment:

```bash
# .env.test
DATABASE_URL=postgresql://user:pass@localhost:5432/rag_test
GCS_BUCKET=test-bucket
GCP_PROJECT_ID=test-project
```

### Test Database

Create isolated test database:

```sql
-- Run once
CREATE DATABASE rag_test;
\c rag_test
CREATE EXTENSION vector;
```

### Cleanup Between Tests

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Clean up test data after each test."""
    yield  # Run test
    
    # Cleanup
    await db.execute("DELETE FROM document_chunks WHERE metadata->>'category' = 'test'")
```

## Debugging Tests

### Verbose Output

```bash
# Show print statements
pytest -v -s

# Show locals on failure
pytest -v -l

# Stop on first failure
pytest -x

# Enter debugger on failure
pytest --pdb
```

### Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

def test_with_logging():
    logging.debug("Test started")
    # Test code
    logging.debug("Test completed")
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/postgres
        run: pytest --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Performance Testing

### Benchmark Reranking

```python
import time

def test_reranking_performance():
    """Test reranking performance on 20 documents."""
    start = time.time()
    
    response = client.post(
        "/search",
        json={
            "query": "test query",
            "top_k": 20,
            "rerank": True,
            "rerank_top_k": 10
        }
    )
    
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 10  # Should complete in <10s (20 docs, 10 parallel)
```

## Troubleshooting Tests

### "Database connection failed"

**Cause:** PostgreSQL not running or wrong DATABASE_URL

**Fix:**
```bash
# Check PostgreSQL status
docker ps | grep postgres

# Verify connection
psql $DATABASE_URL -c "SELECT 1"
```

### "GCS bucket not found"

**Cause:** Test bucket doesn't exist or wrong credentials

**Fix:**
```bash
# Create test bucket
gsutil mb -l us-central1 gs://test-bucket

# Verify credentials
gcloud auth application-default login
```

### "Fixture not found"

**Cause:** Test fixture file missing

**Fix:**
```bash
# Check fixtures exist
ls tests/fixtures/documents/
```

### Tests hang indefinitely

**Cause:** Async fixture not properly awaited

**Fix:**
```python
# Wrong
@pytest.fixture
def async_client():
    return AsyncClient(app=app)

# Correct
@pytest.fixture
async def async_client():
    async with AsyncClient(app=app) as client:
        yield client
```

## Best Practices

1. **Isolate Tests:** Each test should be independent
2. **Use Fixtures:** Share common setup via fixtures
3. **Clean Data:** Remove test data after tests
4. **Fast Tests:** Unit tests < 1s, integration < 5s, e2e < 30s
5. **Descriptive Names:** `test_upload_pdf_creates_chunks_in_db()`
6. **One Assert:** Test one thing per test (when possible)
7. **Markers:** Tag tests for selective execution
8. **Coverage:** Aim for 80%+ coverage
9. **Mock External Services:** Don't call real APIs in unit tests
10. **Deterministic:** Tests should give same results every time
