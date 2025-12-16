# Reranking Tests

Comprehensive test suite for the reranking feature across all test levels.

## Test Structure

```
tests/
├── unit/test_reranking.py              # Unit tests (mocked dependencies)
├── integration/test_reranking_integration.py  # Integration tests (real models)
└── e2e/test_reranking_e2e.py           # End-to-end tests (full system)
```

## Test Levels

### Unit Tests (Fast, No External Dependencies)

**Location:** `tests/unit/test_reranking.py`  
**Marker:** `@pytest.mark.unit`  
**Duration:** ~4 seconds for 18 tests  
**Requirements:** None (all mocked)

```bash
# Run unit tests only
pytest tests/unit/test_reranking.py -v -m unit

# Or all unit tests
pytest -m unit
```

**Coverage:**
- ✅ RerankResult dataclass creation
- ✅ LocalCrossEncoderReranker initialization and lazy loading
- ✅ Reranking logic with mocked model
- ✅ CohereReranker API integration (mocked)
- ✅ RerankingFactory singleton pattern
- ✅ Configuration from environment variables
- ✅ Edge cases (empty docs, cleanup)

**Note:** Cohere tests are skipped if `cohere` package not installed (expected behavior).

---

### Integration Tests (Real Models, Slower)

**Location:** `tests/integration/test_reranking_integration.py`  
**Marker:** `@pytest.mark.integration`  
**Duration:** ~10-15 seconds (first run: +30s for model download)  
**Requirements:**
- Internet connection (first run downloads model)
- ~30MB disk space for TinyBERT model

```bash
# Run integration tests
pytest tests/integration/test_reranking_integration.py -v -m integration
```

**What Gets Downloaded:**
- First run: `cross-encoder/ms-marco-TinyBERT-L-2-v2` (~23MB) from HuggingFace
- Cached in: `~/.cache/huggingface/hub/`
- Subsequent runs use cached model

**Coverage:**
- ✅ Real model loading from HuggingFace
- ✅ Actual inference with cross-encoder
- ✅ Reranking improves document relevance
- ✅ Factory creates working reranker from env vars
- ✅ Edge cases with real model (empty docs, single doc, top_k > docs)

**Test Validation:**
```python
# Example: Verifies Python docs rank higher for Python query
query = "What is Python?"
documents = [
    "Python is a programming language.",  # Should rank high
    "Java is used for enterprise apps.",  # Should rank low
    "Python is popular for ML.",         # Should rank high
]
# Assertion: At least 2 of top 3 are Python-related
```

---

### E2E Tests (Full System, Requires Infrastructure)

**Location:** `tests/e2e/test_reranking_e2e.py`  
**Marker:** `@pytest.mark.e2e`  
**Duration:** ~30-60 seconds  
**Requirements:**
- ✅ Running FastAPI server (`uvicorn src.main:app --reload`)
- ✅ PostgreSQL database with pgvector extension
- ✅ GCP credentials configured (`GOOGLE_APPLICATION_CREDENTIALS`)
- ✅ Vertex AI API enabled
- ✅ `.env.local` with reranking enabled

```bash
# Start server first
uvicorn src.main:app --reload

# In another terminal, run E2E tests
pytest tests/e2e/test_reranking_e2e.py -v -m e2e
```

**Configuration for E2E:**

Update `.env.local`:
```bash
# Enable reranking
RERANKER_ENABLED=true
RERANKER_TYPE=local
RERANKER_MODEL=cross-encoder/ms-marco-TinyBERT-L-2-v2
```

**Coverage:**
- ✅ Query without reranking (baseline)
- ✅ Query with reranking enabled
- ✅ Reranking improves relevance vs baseline
- ✅ Different `top_k` values
- ✅ `rerank_candidates` parameter controls fetch size
- ✅ Reranking disabled by default
- ✅ Performance validation (< 5s per query)
- ✅ Handles empty results gracefully

**Test Flow:**
```
1. Create test corpus
2. Upload 5 documents (Python, ML, Java, JS topics)
3. Query with/without reranking
4. Compare results
5. Cleanup corpus
```

**Example Validation:**
```python
# Query: "Python machine learning frameworks"
# Expected: python_ml.txt ranks highest (contains both Python AND ML)
# Verified: Reranked results contain "TensorFlow" or "PyTorch" in top 3
```

---

## Running All Tests

```bash
# All tests (unit + integration + e2e)
pytest tests/ -v

# Only fast tests (unit)
pytest -m unit

# Only integration tests
pytest -m integration

# Only e2e tests (requires server)
pytest -m e2e

# Skip slow tests
pytest -m "not integration and not e2e"

# Run specific test file
pytest tests/unit/test_reranking.py::TestLocalCrossEncoderReranker::test_rerank -v
```

## Test Markers Summary

| Marker | Speed | Dependencies | Use Case |
|--------|-------|--------------|----------|
| `unit` | ⚡ Fast (~4s) | None (mocked) | CI/CD, pre-commit hooks |
| `integration` | 🐌 Medium (~15s) | Real models | Verify model behavior |
| `e2e` | 🐢 Slow (~60s) | Full stack | Release validation |

## Troubleshooting

### Unit Tests Fail with "No module named 'cohere'"
**Expected:** Cohere tests are skipped (not an error)
```
14 passed, 4 skipped
```

### Integration Tests Slow on First Run
**Expected:** Downloading TinyBERT model (~23MB)
- First run: ~40s
- Subsequent runs: ~10s

### E2E Tests Fail with "Server not running"
**Solution:** Start server first:
```bash
uvicorn src.main:app --reload
```

### E2E Tests Fail with "Failed to create corpus"
**Check:**
1. Database running: `docker-compose up -d postgres`
2. GCP credentials: `echo $GOOGLE_APPLICATION_CREDENTIALS`
3. Vertex AI enabled: `gcloud services enable aiplatform.googleapis.com`

### Model Download Fails (Network Error)
**Solution:** Check internet connection or use cached model:
```bash
# Pre-download model
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-TinyBERT-L-2-v2')"
```

## CI/CD Configuration

Recommended GitHub Actions workflow:

```yaml
- name: Run unit tests
  run: pytest -m unit --cov=src/reranking

- name: Run integration tests
  run: pytest -m integration
  # Only on main branch (slower)
  if: github.ref == 'refs/heads/main'

- name: Run E2E tests
  run: pytest -m e2e
  # Only on release
  if: startsWith(github.ref, 'refs/tags/')
```

## Test Data

### Integration Test Models
- **TinyBERT-L-2-v2:** 23MB, 2-layer, fast inference (~100ms for 5 docs)
- Used instead of MiniLM (120MB) for faster CI/CD

### E2E Test Corpus
Creates 5 test documents:
1. `python_basics.txt` - Python programming fundamentals
2. `python_ml.txt` - Python for ML (TensorFlow, PyTorch)
3. `java_basics.txt` - Java programming
4. `javascript_web.txt` - JavaScript for web
5. `ml_overview.txt` - General ML overview

**Total size:** ~500 tokens  
**Cleanup:** Auto-deleted after tests

## Performance Benchmarks

| Test Level | Total Tests | Duration | Model Download |
|------------|-------------|----------|----------------|
| Unit | 18 | ~4s | None (mocked) |
| Integration | 5 | ~10s | ~30s (first run) |
| E2E | 9 | ~60s | Reuses integration cache |

**Hardware:** MacBook Pro M1, 16GB RAM  
**Network:** 100 Mbps download

## Next Steps

After all tests pass:
1. ✅ Commit test files
2. ✅ Update ROADMAP.md (mark reranking complete)
3. ✅ Update main README.md (document reranking API)
4. ✅ Deploy to staging
5. ✅ Run E2E tests in staging
6. ✅ Deploy to production
