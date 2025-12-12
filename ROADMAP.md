# RAG Lab - Product Roadmap

**Last Updated:** December 11, 2025  
**Current Version:** 0.2.0  
**Status:** Production-ready with core features, missing industry-standard advanced features

---

## 🎯 Current State Assessment

### ✅ Implemented (Production-Ready)

**Core RAG Capabilities:**
- ✅ Multi-format document ingestion (17 formats: PDF, TXT, MD, JSON, XML, CSV, YAML, HTML, logs, code)
- ✅ Smart text extraction (PDF→Markdown, JSON/XML→YAML for LLM optimization)
- ✅ Vector embeddings (Vertex AI text-embedding-005, 768 dimensions)
- ✅ Semantic search (PostgreSQL + pgvector, cosine similarity)
- ✅ Similarity threshold filtering (min_similarity parameter to filter irrelevant results)
- ✅ SHA256 deduplication (prevents duplicate document uploads)
- ✅ Hybrid storage architecture (PostgreSQL for embeddings, GCS for documents - 8.5x cost savings)

**Infrastructure & Operations:**
- ✅ Cloud Run deployment with auto-scaling
- ✅ Multi-cloud portable (works on GCP, AWS, Azure with PostgreSQL)
- ✅ Cost-optimized ($7-12/month for 10k documents)
- ✅ Comprehensive testing (74 tests: 49 unit, 20 e2e, 5 integration)
- ✅ Local development workflow with hot reload
- ✅ File validation (3-tier: strict for PDF, structured for JSON/XML, lenient for text)

---

## ❌ Missing Features (Industry Standard Gaps)

### 1. **Metadata Filtering** 🔴 CRITICAL
**Priority:** P0 (Must Have - Next 2 Weeks)  
**Effort:** 4 hours  
**Impact:** HIGH - Required for production SaaS deployment

**Problem:**  
Currently, `/v1/query` searches across ALL documents without filtering. Cannot implement:
- Multi-tenant isolation (user_id filtering)
- Document categorization (tags, departments)
- Time-based filtering (uploaded_after, created_before)
- Custom business logic (file_type, status, visibility)

**Use Cases:**
```python
# User isolation (multi-tenancy)
POST /v1/query
{
  "query": "pricing strategy",
  "filters": {"user_id": "user123"}
}

# Document type filtering
{
  "query": "contract terms",
  "filters": {"file_type": "pdf", "tags": ["legal"]}
}

# Time-based search
{
  "query": "Q4 2025 report",
  "filters": {
    "uploaded_after": "2025-10-01",
    "uploaded_before": "2025-12-31"
  }
}

# Combined filters
{
  "query": "financial analysis",
  "filters": {
    "user_id": "user123",
    "tags": ["finance", "2025"],
    "file_type": "pdf",
    "department": "accounting"
  }
}
```

**Implementation Plan:**
1. **Database Schema:**
   - Add `metadata JSONB` column to `original_documents` table
   - Create GIN index: `CREATE INDEX idx_metadata ON original_documents USING gin(metadata);`
   - Migrate existing docs: `UPDATE original_documents SET metadata = '{"uploaded_by": "system"}'::jsonb`

2. **API Changes:**
   - Add `filters: Optional[dict]` parameter to `QueryRequest` model
   - Update `search_similar_chunks()` in database.py to accept filters
   - SQL WHERE clause: `WHERE metadata @> $filters::jsonb`
   - Support operators: `@>` (contains), `?` (key exists), `@?` (path exists)

3. **Upload Endpoint:**
   - Accept optional `metadata` in upload request
   - Store in database: `INSERT ... metadata = $metadata::jsonb`
   - Default metadata: `{"uploaded_at": timestamp, "uploaded_by": "api"}`

4. **Testing:**
   - Unit tests: metadata filtering logic
   - E2E tests: multi-tenant isolation validation
   - Performance tests: GIN index query speed

**Example Code:**
```python
# QueryRequest model
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    min_similarity: float = 0.0
    filters: Optional[dict] = None  # NEW

# Database query
async def search_similar_chunks(..., filters: Optional[dict] = None):
    query = """
        SELECT ... FROM document_chunks c
        JOIN original_documents d ON c.original_doc_id = d.id
        WHERE (1 - (c.embedding <=> $1)) >= $3
        AND ($4::jsonb IS NULL OR d.metadata @> $4::jsonb)  -- NEW
        ORDER BY c.embedding <=> $1
        LIMIT $2
    """
    await conn.fetch(query, embedding, top_k, min_similarity, filters)
```

**Benefits:**
- ✅ Multi-tenant SaaS ready (user_id isolation)
- ✅ Document organization (tags, categories)
- ✅ Access control foundation
- ✅ Flexible custom filtering
- ✅ Zero performance impact with GIN index

**Risks:**
- None - JSONB is native PostgreSQL, GIN indexes are performant

---

### 2. **Reranking** 🟡 HIGH
**Priority:** P1 (Should Have - Next Month)  
**Effort:** 6 hours  
**Impact:** MEDIUM - 15-30% quality improvement

**Problem:**  
Vector search alone is suboptimal for ranking. Cross-encoder models significantly improve precision by scoring query-document pairs.

**Solution:**
1. Vector search retrieves top 20-50 candidates (high recall)
2. Cross-encoder reranks candidates by query-document relevance (high precision)
3. Return top 5 best results

**Models:**
- **Local (recommended):** `cross-encoder/ms-marco-MiniLM-L-6-v2` (fast, free, 90MB)
- **Cloud (future):** Vertex AI Ranking API (when available in GA)

**Implementation:**
```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# After vector search
candidates = await vector_search(query, top_k=20)

# Rerank
scores = reranker.predict([(query, c.text) for c in candidates])
reranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

return reranked[:5]  # Top 5 after reranking
```

**Benefits:**
- ✅ Better ranking quality
- ✅ Handles semantic nuances
- ✅ Local model = no API costs
- ✅ Fast inference (10-20ms per pair)

---

### 3. **Hybrid Search (BM25 + Vector)** 🟡 MEDIUM
**Priority:** P2 (Should Have - Next Month)  
**Effort:** 8 hours  
**Impact:** MEDIUM - Better for exact matches

**Problem:**  
Pure vector search fails on:
- Exact product names ("iPhone 16 Pro Max")
- Codes/IDs ("INV-2025-001234")
- Proper nouns ("John Smith", "Microsoft Azure")

**Solution:**  
Combine BM25 (keyword-based) + Vector (semantic):
```
Final Score = 0.7 × vector_similarity + 0.3 × bm25_score
```

**PostgreSQL Implementation:**
```sql
-- Enable extensions
CREATE EXTENSION pg_trgm;

-- Add text search column
ALTER TABLE document_chunks ADD COLUMN text_search tsvector;
CREATE INDEX idx_text_search ON document_chunks USING gin(text_search);

-- Hybrid query
SELECT *,
    (0.7 * (1 - (embedding <=> $query_vector)) +
     0.3 * ts_rank(text_search, to_tsquery($query_keywords))) as score
FROM document_chunks
ORDER BY score DESC
LIMIT 10;
```

**Benefits:**
- ✅ Best of both worlds
- ✅ Handles exact + semantic matches
- ✅ No external dependencies

---

### 4. **Multi-Tenancy / User Isolation** 🔴 CRITICAL
**Priority:** P0 (MUST HAVE - part of Metadata Filtering)  
**Effort:** 2 hours (included in metadata filtering)  
**Impact:** CRITICAL - Security requirement for SaaS

**Implementation:**
- Store `user_id` in metadata during upload
- Filter by `user_id` in all queries
- Row-level security (RLS) in PostgreSQL (optional hardening)

**Security Model:**
```python
# Upload
metadata = {
    "user_id": get_current_user_id(),
    "org_id": get_current_org_id(),
    "visibility": "private"  # or "shared", "public"
}

# Query (automatic injection)
filters = {
    "user_id": current_user.id,
    "visibility": {"$in": ["private", "shared"]}  # Supports user's docs + shared docs
}
```

---

### 5. **Document Updates / Versioning** 🟢 MEDIUM
**Priority:** P3 (Nice to Have - Backlog)  
**Effort:** 8 hours  
**Impact:** MEDIUM - Needed for evolving documents

**Problem:**  
Current implementation: documents are immutable. No way to update content.

**Options:**

**A) Soft Delete + New Version (Recommended):**
```sql
ALTER TABLE original_documents ADD COLUMN deleted_at TIMESTAMP;
ALTER TABLE original_documents ADD COLUMN replaced_by_uuid UUID;

-- Keep history for auditing
-- Queries filter WHERE deleted_at IS NULL
```

**B) Hard Replace:**
- Delete old document + chunks
- Upload new version
- Simpler but loses history

**C) Full Versioning:**
```sql
ALTER TABLE original_documents ADD COLUMN version_number INT DEFAULT 1;
ALTER TABLE original_documents ADD COLUMN parent_uuid UUID;

-- Query specific version
SELECT * WHERE doc_uuid = $uuid AND version_number = $version;

-- Query latest
SELECT * WHERE doc_uuid = $uuid ORDER BY version_number DESC LIMIT 1;
```

---

### 6. **Parent Document Retrieval** 🟢 MEDIUM
**Priority:** P3 (Nice to Have - Backlog)  
**Effort:** 10 hours  
**Impact:** MEDIUM - Better context for LLM generation

**Problem:**  
Small chunks (2000 chars) = high recall but lose context.  
Large chunks (10000 chars) = good context but poor recall.

**Solution:**  
Search with small chunks, return parent chunks:
```
Document
  ├─ Parent Chunk 1 (10000 chars) ────┐
  │   ├─ Child Chunk 1.1 (2000 chars) │ Search these
  │   ├─ Child Chunk 1.2 (2000 chars) │
  │   └─ Child Chunk 1.3 (2000 chars) │
  │                                    │
  └─ Parent Chunk 2 (10000 chars) ────┘
       ├─ Child Chunk 2.1
       └─ Child Chunk 2.2

Search Match: Child 1.2
Return: Parent 1 (full 10000 chars context)
```

**Schema:**
```sql
ALTER TABLE document_chunks ADD COLUMN parent_chunk_index INT;
-- child chunks reference parent chunk in same document
```

---

### 7. **Async Processing** 🟢 LOW
**Priority:** P4 (Nice to Have - Backlog)  
**Effort:** 10 hours  
**Impact:** LOW - UX improvement, not critical

**Problem:**  
Large PDF uploads block HTTP request for 30+ seconds.

**Solution:**  
Background job processing:
```
POST /v1/documents/upload
  ↓
202 Accepted
{
  "job_id": "uuid",
  "status": "processing"
}

GET /v1/jobs/{job_id}
  ↓
{
  "status": "completed",
  "doc_id": 123,
  "doc_uuid": "..."
}
```

**Tech Stack:**
- **Simple:** Cloud Tasks (serverless)
- **Advanced:** Celery + Redis (more features)

---

### 8. **Multi-Query / Query Decomposition** 🟢 LOW
**Priority:** P4 (Optimization - Backlog)  
**Effort:** 3 hours  
**Impact:** LOW - Edge case optimization

**Use Case:**  
Complex queries benefit from decomposition:
```
"Compare Q3 vs Q4 revenue growth trends"
  ↓ LLM decomposition
[
  "Q3 revenue data",
  "Q4 revenue data",
  "revenue growth analysis methodology"
]
  ↓ Search each
3 × vector_search()
  ↓ Merge & deduplicate
Final results
```

---

### 9. **Contextual Compression** 🟢 LOW
**Priority:** P4 (Optimization - Backlog)  
**Effort:** 4 hours  
**Impact:** LOW - Token optimization

**Problem:**  
Return full 2000-char chunks, but only 2-3 sentences are relevant.

**Solution:**  
LLM-based extraction:
```
Chunk: [2000 chars about product features]
Query: "pricing"
  ↓ LLM compression
Output: "Standard: $99/mo. Enterprise: $499/mo. Annual discount: 20%."
```

**Cost:** +1 LLM call per chunk (Gemini Flash = $0.0001/chunk)

---

### 10. **Query Analytics** 🟢 LOW
**Priority:** P4 (Observability - Backlog)  
**Effort:** 6 hours  
**Impact:** LOW - Product insights

**Features:**
- Query logging (text, timestamp, user_id, results_count)
- Popular queries tracking
- Zero-results queries (identify gaps)
- User feedback (thumbs up/down on results)
- A/B testing framework

**Schema:**
```sql
CREATE TABLE query_logs (
    id SERIAL PRIMARY KEY,
    query_text TEXT,
    user_id TEXT,
    filters JSONB,
    results_count INT,
    top_similarity FLOAT,
    latency_ms INT,
    timestamp TIMESTAMP,
    feedback INT  -- +1 (good), -1 (bad), NULL (no feedback)
);
```

---

## 📊 Competitive Analysis

| Feature | RAG Lab | LangChain | LlamaIndex | Pinecone | Weaviate |
|---------|---------|-----------|------------|----------|----------|
| **Core Features** |
| Vector Search | ✅ pgvector | ✅ Multiple | ✅ Multiple | ✅ Native | ✅ Native |
| Multi-format Ingestion | ✅ 17 formats | ⚠️ Basic | ✅ Good | ❌ Manual | ⚠️ Limited |
| Deduplication | ✅ SHA256 | ❌ | ❌ | ❌ | ❌ |
| Smart Extraction | ✅ PDF→MD, JSON→YAML | ⚠️ Basic | ✅ Good | ❌ | ❌ |
| Similarity Threshold | ✅ min_similarity | ⚠️ Manual | ✅ | ✅ | ✅ |
| **Advanced Features** |
| Metadata Filtering | ❌ **MISSING** | ✅ | ✅ | ✅ | ✅ |
| Hybrid Search (BM25+Vector) | ❌ **MISSING** | ✅ | ✅ | ✅ Sparse-Dense | ✅ |
| Reranking | ❌ **MISSING** | ✅ Cohere | ✅ Multiple | ✅ | ✅ |
| Multi-tenancy | ❌ **MISSING** | ⚠️ Manual | ⚠️ Manual | ✅ Namespaces | ✅ Multi-tenant |
| Document Versioning | ❌ | ⚠️ Manual | ❌ | ❌ | ⚠️ Limited |
| **Infrastructure** |
| Cost Optimization | ✅ Hybrid Storage | ❌ | ❌ | ⚠️ Expensive | ⚠️ Expensive |
| Multi-cloud Portable | ✅ PostgreSQL | ✅ | ✅ | ❌ Cloud-only | ❌ Cloud-only |
| Auto-scaling | ✅ Cloud Run | ⚠️ Manual | ⚠️ Manual | ✅ | ✅ |
| Testing Coverage | ✅ 74 tests | ⚠️ Varies | ⚠️ Varies | ⚠️ Proprietary | ⚠️ Proprietary |

**Legend:** ✅ Full Support | ⚠️ Partial/Manual | ❌ Not Available

**Key Takeaways:**
- **Unique Strengths:** SHA256 deduplication, cost-optimized hybrid storage, multi-cloud portability, comprehensive testing
- **Critical Gaps:** Metadata filtering, multi-tenancy (P0 - must fix)
- **Competitive Gaps:** Reranking, hybrid search (P1 - should add)
- **Advanced Features:** Versioning, parent retrieval (P3 - nice to have)

---

## 🎯 Recommended Roadmap

### Phase 1: Production Readiness (Next 2 Weeks)
**Goal:** Make RAG Lab production-ready for multi-tenant SaaS

1. **Metadata Filtering + Multi-Tenancy** (4 hours) 🔴 P0
   - Add JSONB metadata column with GIN index
   - Implement filters parameter in query API
   - Add user_id to upload metadata
   - Update all queries to filter by metadata
   - Write tests for multi-tenant isolation

**Deliverable:** Production-ready multi-tenant RAG system

---

### Phase 2: Quality Improvements (Next Month)
**Goal:** Match industry-standard search quality

2. **Reranking** (6 hours) 🟡 P1
   - Integrate cross-encoder/ms-marco-MiniLM-L-6-v2
   - Add reranking step after vector search
   - Benchmark quality improvements
   - Optional: make reranking toggleable

3. **Hybrid Search** (8 hours) 🟡 P1
   - Enable pg_trgm extension
   - Add tsvector column + GIN index
   - Implement weighted scoring (0.7 vector + 0.3 BM25)
   - Add keyword extraction from queries
   - Test on exact match scenarios

**Deliverable:** Best-in-class search quality

---

### Phase 3: Advanced Features (Backlog)
**Goal:** Differentiation and optimization

4. **Document Versioning** (8 hours) 🟢 P3
   - Implement soft delete + replacement tracking
   - Add version history API endpoints
   - Support rollback to previous versions

5. **Parent Document Retrieval** (10 hours) 🟢 P3
   - Add parent-child chunk relationship
   - Implement hierarchical chunking
   - Return parent context for better LLM generation

6. **Async Processing** (10 hours) 🟢 P4
   - Implement background job queue (Cloud Tasks)
   - Return 202 Accepted for uploads
   - Add job status polling endpoint
   - Webhook notifications on completion

7. **Query Analytics** (6 hours) 🟢 P4
   - Log all queries with metadata
   - Build analytics dashboard
   - Implement user feedback collection
   - Track popular queries and zero-result cases

---

## 🚀 Quick Wins (Immediate Impact)

### 1. Metadata Filtering (4 hours)
**Why First:**
- Highest impact/effort ratio
- Unblocks multi-tenancy
- Required for production SaaS
- Simple implementation (native PostgreSQL JSONB)

**Next Steps:**
1. Add metadata column to schema
2. Update QueryRequest model
3. Modify search_similar_chunks() SQL
4. Add tests
5. Update API documentation

### 2. Add Example Filters to README (30 minutes)
**Why:**
- Documents intended usage patterns
- Educates users on best practices
- Low effort, high clarity

---

## 📝 Implementation Notes

### Metadata Filtering Deep Dive

**Schema Migration:**
```sql
-- Add metadata column
ALTER TABLE original_documents 
ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;

-- Create GIN index for fast filtering
CREATE INDEX idx_documents_metadata 
ON original_documents USING gin(metadata);

-- Optional: Add specific indexes for common filters
CREATE INDEX idx_documents_user_id 
ON original_documents ((metadata->>'user_id'));
```

**API Examples:**
```bash
# Upload with metadata
curl -X POST /v1/documents/upload \
  -F "file=@report.pdf" \
  -F "metadata={\"user_id\":\"user123\",\"tags\":[\"finance\",\"Q4\"],\"department\":\"accounting\"}"

# Query with filters
curl -X POST /v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "revenue analysis",
    "top_k": 5,
    "min_similarity": 0.5,
    "filters": {
      "user_id": "user123",
      "tags": ["finance"]
    }
  }'

# Complex filtering (JSONB operators)
{
  "filters": {
    "user_id": "user123",           # Exact match
    "tags": ["finance", "2025"],    # Array contains
    "created_at": {                 # Range query
      ">=": "2025-01-01",
      "<=": "2025-12-31"
    }
  }
}
```

**PostgreSQL JSONB Operators:**
- `@>` - Contains (filter matches if document metadata contains all filter keys)
- `?` - Key exists
- `->` - Get value
- `->>` - Get value as text
- `@?` - JSONPath query

---

## 🎓 Learning Resources

**Metadata Filtering:**
- PostgreSQL JSONB: https://www.postgresql.org/docs/current/datatype-json.html
- GIN Indexes: https://www.postgresql.org/docs/current/gin-intro.html

**Reranking:**
- Cross-Encoders: https://www.sbert.net/examples/applications/cross-encoder/README.html
- MS MARCO: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2

**Hybrid Search:**
- BM25: https://en.wikipedia.org/wiki/Okapi_BM25
- PostgreSQL Full-Text Search: https://www.postgresql.org/docs/current/textsearch.html

---

## 🔄 Version History

**v0.2.0 (Current - Dec 11, 2025):**
- ✅ Inline unit test fixtures
- ✅ Similarity threshold filtering (min_similarity)
- ✅ 74 comprehensive tests (49 unit, 20 e2e, 5 integration)
- ✅ Enhanced Swagger documentation

**v0.1.0 (Initial Release):**
- ✅ Core RAG pipeline (upload, chunk, embed, search)
- ✅ Multi-format support (17 formats)
- ✅ Hybrid storage (PostgreSQL + GCS)
- ✅ SHA256 deduplication
- ✅ Cloud Run deployment

**v0.3.0 (Planned - Next 2 Weeks):**
- 🔄 Metadata filtering + multi-tenancy

---

## 📞 Next Steps

**To implement metadata filtering:**
1. Review this roadmap
2. Start new conversation: "Implement metadata filtering from ROADMAP.md"
3. Agent will have full context and can proceed with implementation

**To implement other features:**
1. Reference specific section from this roadmap
2. Provide additional requirements/constraints
3. Agent implements with tests and documentation

---

**Status:** Ready for Phase 1 implementation
**Contact:** Start new conversation with "Continue from ROADMAP.md Phase 1"
