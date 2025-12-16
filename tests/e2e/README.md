# E2E Test Suite - Selective Execution Guide

## CRITICAL: Test Independence via Explicit Cleanup

**The E2E suite uses EXPLICIT cleanup tests, NOT autouse fixtures!**

- `test_00_cleanup_before` - First test, removes leftover documents
- `test_99_cleanup_after` - Last test, removes test documents

**Why this matters:**
- You can skip cleanup via markers: `-m "not cleanup"`
- You can upload ONCE, then run reranking tests MANY times
- No "autouse fixture magic" - explicit control

## Iterative Development Workflow

### 1️⃣ Upload documents once:
```bash
pytest tests/e2e/test_full_rag_workflow.py -m upload -v
```

### 2️⃣ Run reranking tests many times (no re-upload):
```bash
pytest tests/e2e/test_full_rag_workflow.py -m reranking -v
pytest tests/e2e/test_full_rag_workflow.py -m reranking -v  # Again!
pytest tests/e2e/test_full_rag_workflow.py -m reranking -v  # Again!
```

### 3️⃣ Clean up when done:
```bash
pytest tests/e2e/test_full_rag_workflow.py -m cleanup -v
```

**OR run full suite with cleanup:**
```bash
pytest tests/e2e/test_full_rag_workflow.py -v  # Includes cleanup
```

## Test Stages

The E2E test suite is organized into logical stages using pytest markers:

| Marker | Stage | Tests | Description |
|--------|-------|-------|-------------|
| `cleanup` | Pre/Post Cleanup | 2 tests | test_00_cleanup_before, test_99_cleanup_after |
| `upload` | Document Upload | 11 tests | Uploads TXT, PDF, MD, JSON, HTML, YAML, XML, CSV, LOG + technical doc + story (keyword trap) |
| `security` | Security Tests | 1 test | Protected metadata fields validation |
| `list` | Document Listing | 1 test | List all documents |
| `metadata_filter` | Metadata Filtering | 9 tests | User, department, tags, priority, complex filters |
| `semantic_search` | Semantic Search | 7 tests | Topic-based queries (products, art, compliance, etc.) |
| `reranking` | Reranking | 4 tests | Gemini LLM batch reranking quality, performance & deterministic keyword trap test |
| `download` | Document Download | 1 test | Download original files |
| `storage` | Storage Verification | 1 test | GCS storage validation |

## Selective Execution

### Run specific stage:
```bash
# Upload documents only
pytest tests/e2e/test_full_rag_workflow.py -m upload -v

# Reranking tests only (after uploads!)
pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v

# Semantic search only
pytest tests/e2e/test_full_rag_workflow.py -m semantic_search -v

# Metadata filtering only
pytest tests/e2e/test_full_rag_workflow.py -m metadata_filter -v
```

### Run multiple stages:
```bash
# Upload + list + semantic search
pytest tests/e2e/test_full_rag_workflow.py -m "upload or list or semantic_search" -v

# Everything except cleanup (leaves documents for inspection)
pytest tests/e2e/test_full_rag_workflow.py -m "e2e and not cleanup" -v

# Only reranking with uploads (fastest reranking validation)
pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v
```

### Skip stages:
```bash
# Skip slow reranking tests
pytest tests/e2e/test_full_rag_workflow.py -m "e2e and not reranking" -v

# Skip cleanup (preserve documents)
pytest tests/e2e/test_full_rag_workflow.py -m "e2e and not cleanup" -v
```

## Dependencies

⚠️ **CRITICAL:** Tests depend on documents uploaded by earlier stages!

### BEST PRACTICE: Iterative development

**Upload once, test many times:**
```bash
# 1. Upload test documents (run once)
pytest tests/e2e/test_full_rag_workflow.py -m upload -v

# 2. Run your feature tests (run many times)
pytest tests/e2e/test_full_rag_workflow.py -m reranking -v
pytest tests/e2e/test_full_rag_workflow.py -m semantic_search -v
pytest tests/e2e/test_full_rag_workflow.py::test_05h_query_with_reranking -v

# 3. Clean up when done
pytest tests/e2e/test_full_rag_workflow.py -m cleanup -v
```

**This is THE RECOMMENDED workflow for development!**

### Safe execution patterns:

1. **Full suite** (safest):
   ```bash
   pytest tests/e2e/test_full_rag_workflow.py -v
   ```

2. **Upload + specific stage**:
   ```bash
   # Reranking needs documents
   pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v
   
   # Semantic search needs documents
   pytest tests/e2e/test_full_rag_workflow.py -m "upload or semantic_search" -v
   ```

3. **Skip cleanup for debugging**:
   ```bash
   pytest tests/e2e/test_full_rag_workflow.py -m "e2e and not cleanup" -v
   # Documents remain in DB/GCS for inspection
   ```

### Unsafe execution (will fail):

❌ Don't run reranking without uploads:
```bash
pytest tests/e2e/test_full_rag_workflow.py -m reranking -v
# FAILS: No documents to rerank!
```

❌ Don't run single test from middle of suite:
```bash
pytest tests/e2e/test_full_rag_workflow.py::test_05h_query_with_reranking -v
# FAILS: Cleanup fixture deleted documents!
```

## Reranking Tests

Three reranking tests validate Gemini LLM batch reranking:

| Test | Purpose | Expected Time |
|------|---------|---------------|
| `test_05h` | Keyword ambiguity resolution | ~10-15s |
| `test_05i` | Relevance improvement validation | ~10-15s |
| `test_05j` | Performance test (20 candidates) | ~15-20s |

**Batch mode performance:**
- 10 documents: ~4-5 seconds (single API call)
- 20 documents: ~15-20 seconds (single API call)
- Old sequential: 10 docs = 80s, 20 docs = 160s

### Run only reranking:
```bash
# With uploads (required!)
pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v

# Show detailed output
pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v -s
```

## List Available Markers

```bash
pytest --markers | grep -A1 "e2e\|upload\|reranking"
```

## Tips

1. **Fast reranking validation:** `-m "upload or reranking"` (uploads 9 docs + runs 3 reranking tests)
2. **Debug single stage:** Add `-s` flag to see print statements
3. **Preserve documents:** Use `-m "e2e and not cleanup"` or `--no-cleanup` flag
4. **Performance testing:** Focus on `test_05j` for batch performance validation

## Examples

### Develop reranking feature:
```bash
# Fast iteration: upload + reranking only
pytest tests/e2e/test_full_rag_workflow.py -m "upload or reranking" -v -s

# Full validation with semantic search
pytest tests/e2e/test_full_rag_workflow.py -m "upload or semantic_search or reranking" -v
```

### Test metadata filters:
```bash
pytest tests/e2e/test_full_rag_workflow.py -m "upload or metadata_filter" -v
```

### Quick smoke test:
```bash
pytest tests/e2e/test_full_rag_workflow.py -m "upload or list" -v
```
