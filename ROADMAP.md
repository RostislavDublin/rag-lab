# RAG Lab - Product Roadmap

**Last Updated:** December 19, 2025  
**Current Version:** 0.2.1  
**Status:** Production-ready with hybrid search Phase 2 complete. Models unified to gemini-2.5-flash-lite (extraction + reranking). All env vars now required (no defaults). BigQuery billing analytics ready. All 194 tests passing. **Next: Phase 3 (BM25 query integration) or Metadata Filtering.**

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
- ✅ Metadata filtering (MongoDB Query Language with 12 operators: $and, $or, $not, $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $all, $exists)
- ✅ **Hybrid Search Phase 2 (Upload Integration):** BM25 index generation, LLM summary/keywords extraction, PostgreSQL schema migration (summary TEXT, keywords TEXT[], token_count INTEGER + GIN index), GCS bm25_doc_index.json storage, Snowball stemming with stopwords filtering

**Infrastructure & Operations:**
- ✅ Cloud Run deployment with auto-scaling
- ✅ Multi-cloud portable (works on GCP, AWS, Azure with PostgreSQL)
- ✅ Cost-optimized ($7-12/month for 10k documents)
- ✅ Comprehensive testing (194 tests: 134 unit, 23 integration, 37 e2e - all passing)
- ✅ Local development workflow with hot reload
- ✅ File validation (3-tier: strict for PDF, structured for JSON/XML, lenient for text)
- ✅ **LLM Models:** Unified to `gemini-2.5-flash-lite` for extraction and reranking (100% success rate, 30x faster than gemini-2.5-flash, cheaper)
- ✅ **Configuration:** All env vars required (no defaults in code), explicit .env.local setup
- ✅ **BigQuery Billing Analytics:** OAuth-based query tool (scripts/query_billing.py), dataset: myai-475419.billing_export, waiting for data (24-48hrs)

---

## ❌ Missing Features (Industry Standard Gaps)

**Note:** Metadata Filtering and Reranking are now ✅ IMPLEMENTED (Dec 2025).

### 1. **Hybrid Search (BM25 + Vector)** ✅ Phase 2 COMPLETE | ⏳ Phase 3 NEXT
**Priority:** P0 (Current Sprint - Week of Dec 16-22, 2025)  
**Effort:** 17-26 hours total (5 phases) | **Phase 2: 8 hours DONE** | **Phase 3: 4-6 hours remaining**  
**Impact:** HIGH - Better retrieval quality for keyword + semantic queries  
**Blueprint:** [docs/hybrid-search.md](docs/hybrid-search.md) ← **Detailed design document**

**Current Status:** ✅ Phase 2 Complete (Upload Integration) → 🚧 Phase 3 Next (Query Integration)

**Phase 2 Completed (December 17-18, 2025):**
- ✅ Database schema migration: summary TEXT, keywords TEXT[], token_count INTEGER
- ✅ GIN index on keywords array for fast filtering
- ✅ BM25 tokenizer with Snowball stemming (nltk) + stopwords filtering (34 words)
- ✅ BM25 index builder: document-level term frequency aggregation
- ✅ **LLM extraction:** gemini-2.5-flash-lite (4.2x cheaper, 100% reliable) ~$0.000225/doc
- ✅ **Retry logic:** 5 attempts with exponential backoff (1s, 2s, 4s, 8s, 16s)
- ✅ **Model stability:** Flash-lite: 100% success vs Flash: 90% (JSON parse errors)
- ✅ GCS upload: bm25_doc_index.json (1-5KB per document)
- ✅ Upload endpoint integration: full pipeline working
- ✅ API endpoints updated: /v1/documents returns summary/keywords/token_count
- ✅ Log retention fix: keeps last 5 files (was accumulating 50+)
- ✅ **All tests passing:** 194 passed (134 unit, 23 integration, 37 e2e)

**Model Selection (Dec 18, 2025):**
- **Extraction:** gemini-2.5-flash-lite ($2.25/10K docs) - 100% reliable, complete JSON every time
- **Reranking:** gemini-2.5-flash (stable for search, NOT for extraction due to 10% JSON errors)
- **Environment vars:** EMBEDDING_MODEL, RERANKER_MODEL, LLM_EXTRACTION_MODEL (independent optimization)

**Problem:**  
Pure vector search struggles with:
- Exact product names ("iPhone 16 Pro Max")
- Codes/IDs ("INV-2025-001234")
- Proper nouns ("John Smith", "Microsoft Azure")
- Technical terms that must match exactly ("Kubernetes", "PostgreSQL")

**Solution:**  
Hybrid search combining:
- **Vector search** (chunk-level, semantic similarity)
- **Simplified BM25** (document-level, keyword matching, no global IDF)
- **RRF fusion** (Reciprocal Rank Fusion to combine rankings)
- **LLM keywords** (compensate missing IDF with semantic importance)

**Architecture:**
```
Upload Flow:
  1. Extract text → chunk → generate embeddings
  2. LLM generates summary (2-3 sentences) + keywords (10-15 terms)
  3. Save to PostgreSQL: summary, keywords, token_count
  4. Compute term_frequencies for full document
  5. Save to GCS: bm25_doc_index.json (only term_frequencies!)

Search Flow:
  1. Vector search (top-100 chunks, PostgreSQL)
  2. Fetch bm25_doc_index.json from GCS (parallel batch)
  3. BM25 scoring with keyword boosting (1.5x for LLM keywords)
  4. RRF fusion: score = Σ 1/(60 + rank_i)
  5. Optional cross-encoder reranking (existing)
```

**Benefits:**
- ✅ Best of both worlds (semantic + keyword)
- ✅ No distributed state (Simplified BM25, no global IDF)
- ✅ Summary in search results (better UX)
- ✅ Keyword filtering ready (`WHERE 'Kubernetes' = ANY(keywords)`)
- ✅ Existing filter_parser compatible
- ✅ No external dependencies

---

### 2. **Multi-Tenancy / User Isolation** 🔴 CRITICAL
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

### 3. **Schema Migration System** 🟡 HIGH
**Priority:** P1 (Next Quarter - Infrastructure Improvement)  
**Effort:** 12-16 hours  
**Impact:** HIGH - Production operations requirement

**Problem:**  
Currently using `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS` in application code (`init_schema()`).
Issues:
- Schema changes mixed with application runtime
- No version tracking
- No rollback capability
- Difficult to test migrations
- Cannot verify schema state before deployment

**Solution:**  
Implement versioned migration system:

**PostgreSQL Migrations:**
- **Tool:** Alembic (industry standard for async Python + PostgreSQL)
- **Versions:** Track in `alembic_version` table
- **Migrations:** `deployment/migrations/versions/001_initial.py`, `002_hybrid_search.py`
- **Commands:** `alembic upgrade head`, `alembic downgrade -1`

**GCS Schema Versioning:**
- **Metadata:** `gs://bucket/.schema_version.json` → `{"version": 2, "updated_at": "2025-12-17"}`
- **Migrations:** `deployment/migrations/gcs/001_initial_structure.py`, `002_add_bm25_index.py`
- **Runner:** Custom script checks version, applies needed migrations

**Migration Workflow:**
```bash
# 1. Deploy infrastructure (once)
./deployment/setup-infrastructure.sh

# 2. Run migrations (separate step, before app deploy)
alembic upgrade head                    # PostgreSQL
python deployment/migrate_gcs.py        # GCS schema

# 3. Deploy application (uses ready schema, no init_schema())
./deployment/deploy-cloudrun.sh
```

**Benefits:**
- ✅ Separation of concerns (provisioning vs runtime)
- ✅ Version tracking and history
- ✅ Rollback capability
- ✅ Testable migrations (can test on staging)
- ✅ Schema drift detection
- ✅ Team collaboration (clear migration history in git)

---

### 4. **Document Updates / Versioning** 🟢 MEDIUM
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

### 5. **Parent Document Retrieval** 🟢 MEDIUM
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

### 6. **Async Processing** 🟢 LOW
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

### 7. **Multi-Query / Query Decomposition** 🟢 LOW
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

### 8. **Contextual Compression** 🟢 LOW
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

### 9. **Query Analytics** 🟢 LOW
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
| Metadata Filtering | ✅ MongoDB Query Language | ✅ | ✅ | ✅ | ✅ |
| Hybrid Search (BM25+Vector) | ❌ **TODO** | ✅ | ✅ | ✅ Sparse-Dense | ✅ |
| Reranking | ❌ **TODO** | ✅ Cohere | ✅ Multiple | ✅ | ✅ |
| Multi-tenancy | ✅ X-End-User-ID + TRUSTED_SAs | ⚠️ Manual | ⚠️ Manual | ✅ Namespaces | ✅ Multi-tenant |
| Document Versioning | ❌ | ⚠️ Manual | ❌ | ❌ | ⚠️ Limited |
| **Infrastructure** |
| Cost Optimization | ✅ Hybrid Storage | ❌ | ❌ | ⚠️ Expensive | ⚠️ Expensive |
| Multi-cloud Portable | ✅ PostgreSQL | ✅ | ✅ | ❌ Cloud-only | ❌ Cloud-only |
| Auto-scaling | ✅ Cloud Run | ⚠️ Manual | ⚠️ Manual | ✅ | ✅ |
| Testing Coverage | ✅ 74 tests | ⚠️ Varies | ⚠️ Varies | ⚠️ Proprietary | ⚠️ Proprietary |

**Legend:** ✅ Full Support | ⚠️ Partial/Manual | ❌ Not Available

**Key Takeaways:**
- **Unique Strengths:** SHA256 deduplication, cost-optimized hybrid storage, multi-cloud portability, comprehensive testing, MongoDB-style filtering
- **Production Ready:** Metadata filtering, multi-tenancy, X-End-User-ID security (Phase 1 COMPLETE)
- **Competitive Gaps:** Reranking, hybrid search (P1 - should add)
- **Advanced Features:** Versioning, parent retrieval (P3 - nice to have)

---

## 🎯 Recommended Roadmap

### Phase 1: Production Readiness (Next 2 Weeks)
**Goal:** Make RAG Lab production-ready for multi-tenant SaaS

1. **Metadata Filtering + Multi-Tenancy** ✅ COMPLETED (Dec 13, 2025)
   - ✅ Add JSONB metadata column with GIN index
   - ✅ Implement filters parameter in query API (MongoDB Query Language)
   - ✅ Add user_id to upload metadata
   - ✅ Update all queries to filter by metadata
   - ✅ Write tests for multi-tenant isolation
   
2. **Security: X-End-User-ID Access Control** ✅ COMPLETED (Dec 15, 2025)
   - ✅ Added `TRUSTED_SERVICE_ACCOUNTS` config parameter
   - ✅ JWT validation: only whitelisted service accounts can set X-End-User-ID
   - ✅ Regular users: X-End-User-ID ignored (403 Forbidden if attempted)
   - ✅ Unit tests: 4 security tests covering delegation scenarios
   - ✅ E2E tests: All 30 tests pass with security enabled
   - ✅ Documentation: README and .env.local.example updated
   - **Impact:** CRITICAL security fix - prevents impersonation attacks in production

**Deliverable:** Production-ready multi-tenant RAG system with secure user isolation

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
  -F "metadata={\"user_id\":\"user123\",\"tags\":[\"finance\",\"Q4\"],\"department\":\"accounting\",\"status\":\"approved\"}"

# Simple filter query
curl -X POST /v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "revenue analysis",
    "top_k": 5,
    "min_similarity": 0.5,
    "filters": {
      "user_id": "user123",
      "tags": {"$in": ["finance", "accounting"]}
    }
  }'

# Complex filter with AND/OR/NOT
curl -X POST /v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "contract terms",
    "filters": {
      "$and": [
        {"user_id": "user123"},
        {
          "$or": [
            {"tags": {"$all": ["legal", "reviewed"]}},
            {"department": "legal"}
          ]
        },
        {
          "$not": {
            "$or": [
              {"status": "archived"},
              {"confidentiality": "top-secret"}
            ]
          }
        },
        {"created_at": {"$gte": "2025-01-01"}}
      ]
    }
  }'

# Range queries
curl -X POST /v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quarterly reports",
    "filters": {
      "created_at": {
        "$gte": "2025-10-01",
        "$lt": "2026-01-01"
      },
      "score": {"$gte": 80}
    }
  }'
```

**MongoDB → PostgreSQL Mapping:**

| MongoDB Filter | PostgreSQL WHERE Clause | Example |
|----------------|-------------------------|---------|
| `{"field": "value"}` | `metadata->>'field' = 'value'` | Exact match |
| `{"field": {"$eq": "value"}}` | `metadata->>'field' = 'value'` | Explicit equality |
| `{"field": {"$ne": "value"}}` | `metadata->>'field' != 'value'` | Not equal |
| `{"field": {"$gt": 100}}` | `(metadata->>'field')::numeric > 100` | Greater than |
| `{"field": {"$gte": 100}}` | `(metadata->>'field')::numeric >= 100` | Greater or equal |
| `{"field": {"$lt": 100}}` | `(metadata->>'field')::numeric < 100` | Less than |
| `{"field": {"$lte": 100}}` | `(metadata->>'field')::numeric <= 100` | Less or equal |
| `{"tags": {"$in": ["a","b"]}}` | `metadata->'tags' ?| array['a','b']` | Array contains ANY |
| `{"tags": {"$all": ["a","b"]}}` | `metadata->'tags' ?& array['a','b']` | Array contains ALL |
| `{"tags": {"$nin": ["a","b"]}}` | `NOT (metadata->'tags' ?| array['a','b'])` | Array contains NONE |
| `{"field": {"$exists": true}}` | `metadata ? 'field'` | Key exists |
| `{"field": {"$exists": false}}` | `NOT (metadata ? 'field')` | Key doesn't exist |
| `{"$and": [A, B]}` | `(A_clause) AND (B_clause)` | Logical AND |
| `{"$or": [A, B]}` | `(A_clause) OR (B_clause)` | Logical OR |
| `{"$not": A}` | `NOT (A_clause)` | Logical NOT |

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

## 📞 Next Steps & Priorities

### 🎯 Immediate Next Action (Choose One):

**Option A: Hybrid Search Phase 3 - BM25 Query Integration** (Technical Completion)
- **Effort:** 2-3 hours
- **Impact:** Complete hybrid search feature (vector + BM25 + RRF fusion)
- **Value:** Better retrieval quality, keyword+semantic search combined
- **Tasks:**
  1. Load BM25 index from GCS in `/v1/query` endpoint
  2. Implement BM25 scoring (TF-IDF with stemming)
  3. RRF fusion (vector + BM25 scores)
  4. E2E tests for hybrid queries
  5. Documentation update

**Option B: Metadata Filtering** (Product/SaaS Critical)
- **Effort:** 4 hours
- **Impact:** Enable multi-tenancy, production SaaS deployment
- **Value:** User isolation, document categorization, time-based filtering
- **Tasks:**
  1. Add `metadata JSONB` column to PostgreSQL
  2. Implement MongoDB-style filter parser
  3. Update `/v1/query` and `/v1/upload` endpoints
  4. E2E tests for multi-tenant isolation
  5. Documentation update

**Option C: BigQuery Billing Analytics** (Cost Optimization)
- **Status:** Infrastructure ready, waiting for data (Dec 19-20)
- **Next:** Analyze costs when data arrives, optimize expensive operations
- **Tasks:**
  1. Query billing data (scripts/query_billing.py)
  2. Identify cost drivers (Gemini API, embeddings, storage)
  3. Create cost dashboard queries
  4. Optimize if needed

### 🗓️ Recommended Sequence:

1. **Today (Dec 19):** Wait for billing data → analyze costs
2. **Next session:** Choose Phase 3 (technical) OR Metadata Filtering (product)
3. **Future:** Complete whichever wasn't chosen in step 2

---

## 📝 Implementation Commands

**To implement Hybrid Search Phase 3:**
```
"Implement Hybrid Search Phase 3 from ROADMAP.md - BM25 query integration with RRF fusion"
```

**To implement Metadata Filtering:**
```
"Implement metadata filtering from ROADMAP.md - MongoDB-style filters for multi-tenancy"
```

**To analyze billing data:**
```
"Analyze BigQuery billing data - identify cost drivers and optimize"
```

---

**Status:** Ready for Phase 1 implementation
**Contact:** Start new conversation with "Continue from ROADMAP.md Phase 1"
