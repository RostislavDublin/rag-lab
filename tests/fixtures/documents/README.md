# Test fixtures for integration testing

This directory contains test documents for RAG system integration testing.

## Documents

1. **rag_architecture_guide.txt** (3.5KB)
   - Content: RAG system architecture, components, best practices
   - Keywords: RAG, embeddings, vector search, chunking, retrieval
   - Use for: Testing RAG concept queries

2. **gcp_services_overview.txt** (6.2KB)
   - Content: Google Cloud Platform services (Compute, Storage, AI/ML)
   - Keywords: Cloud Run, Cloud SQL, Vertex AI, Gemini, GCS
   - Use for: Testing GCP-specific queries

3. **fastapi_best_practices.txt** (5.8KB)
   - Content: FastAPI development patterns and best practices
   - Keywords: FastAPI, Python, Pydantic, async, API, testing
   - Use for: Testing Python/FastAPI queries

4. **pgvector_complete_guide.txt** (7.1KB)
   - Content: PostgreSQL pgvector extension guide
   - Keywords: pgvector, PostgreSQL, vector database, similarity search, indexing
   - Use for: Testing database/vector search queries

## Test Scenarios

### 1. Single Document Retrieval
Query: "What is RAG?"
Expected: Should retrieve chunks from rag_architecture_guide.txt

### 2. Multi-Document Context
Query: "How do I deploy a FastAPI application to GCP?"
Expected: Should retrieve from both fastapi_best_practices.txt and gcp_services_overview.txt

### 3. Technical Depth
Query: "How does HNSW indexing work in pgvector?"
Expected: Should retrieve detailed section from pgvector_complete_guide.txt

### 4. Cost Information
Query: "What is the pricing for Cloud Run?"
Expected: Should retrieve pricing section from gcp_services_overview.txt

### 5. Code Examples
Query: "Show me how to handle file uploads in FastAPI"
Expected: Should retrieve code snippet from fastapi_best_practices.txt

### 6. Comparison Queries
Query: "What's the difference between IVFFlat and HNSW indexes?"
Expected: Should retrieve comparison section from pgvector_complete_guide.txt

### 7. Best Practices
Query: "What are the best practices for chunking in RAG?"
Expected: Should retrieve best practices section from rag_architecture_guide.txt

## Usage in Tests

```python
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "documents"

@pytest.fixture
def rag_guide():
    return (FIXTURES_DIR / "rag_architecture_guide.txt").read_text()

@pytest.fixture
def gcp_overview():
    return (FIXTURES_DIR / "gcp_services_overview.txt").read_text()

# Integration test example
async def test_document_upload_and_query():
    # Upload test documents
    for doc in FIXTURES_DIR.glob("*.txt"):
        response = await client.post(
            "/upload",
            files={"file": doc.open("rb")}
        )
        assert response.status_code == 200
    
    # Query
    response = await client.post(
        "/query",
        json={"query": "What is RAG?", "top_k": 5}
    )
    assert response.status_code == 200
    assert "Retrieval-Augmented Generation" in response.json()["results"]
```

## Document Statistics

| Document | Size | Lines | Words | Unique Terms |
|----------|------|-------|-------|--------------|
| rag_architecture_guide.txt | 3.5KB | 85 | 550 | ~200 |
| gcp_services_overview.txt | 6.2KB | 165 | 980 | ~350 |
| fastapi_best_practices.txt | 5.8KB | 310 | 850 | ~300 |
| pgvector_complete_guide.txt | 7.1KB | 380 | 1100 | ~400 |

Total: ~22.6KB, 4 documents, suitable for integration testing without excessive API costs.
