# RAG Lab - Product Roadmap

**Last Updated:** December 20, 2025  
**Current Version:** 0.3.0  
**Status:** Production-ready with **Hybrid Search COMPLETE** (all 3 phases done). Vector + BM25 + RRF fusion working in query endpoint. 69 tests passing (38 e2e, 23 integration, 8 unit). **Next: Multi-Tenancy (P0) or Schema Migrations (P1).**

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
- ✅ **Hybrid Search (All 3 Phases COMPLETE):** BM25 index generation, LLM summary/keywords extraction, PostgreSQL schema (summary, keywords, token_count + GIN index), GCS bm25_doc_index.json storage, Snowball stemming, **Query endpoint integration (vector + BM25 + RRF fusion), use_hybrid parameter, _hybrid_search() function**

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

**Note:** Metadata Filtering, Reranking, and **Hybrid Search** are now ✅ IMPLEMENTED (Dec 2025).

### 1. ~~**Hybrid Search (BM25 + Vector)**~~ ✅ **COMPLETE - ALL 3 PHASES DONE (Dec 20, 2025)**
**Status:** ✅ Production-ready and tested (38 e2e tests passing)  
**Completed:** December 17-20, 2025 (10 hours total)  
**Impact:** HIGH - Better retrieval quality for keyword + semantic queries  
**Blueprint:** [docs/hybrid-search.md](docs/hybrid-search.md) ← **Detailed design document**

**All Phases Completed:**

**Phase 1: Planning & Design (2 hours) - Dec 16:**
- ✅ Architecture design: Simplified BM25 (no global IDF)
- ✅ Blueprint document created (docs/hybrid-search.md)
- ✅ Cost analysis: ~$0.000225/doc for LLM extraction

**Phase 2: Upload Integration (4 hours) - Dec 17-18:**
- ✅ Database schema migration: summary TEXT, keywords TEXT[], token_count INTEGER
- ✅ GIN index on keywords array for fast filtering
- ✅ BM25 tokenizer with Snowball stemming (nltk) + stopwords filtering (34 words)
- ✅ BM25 index builder: document-level term frequency aggregation
- ✅ LLM extraction: gemini-2.5-flash-lite (100% reliable, ~$0.000225/doc)
- ✅ GCS upload: bm25_doc_index.json (1-5KB per document)
- ✅ Upload endpoint integration

**Phase 3: Query Integration (6 hours) - Dec 19-20:**
- ✅ _hybrid_search() function implementation
- ✅ Vector search (top-100 chunks) → BM25 scoring → RRF fusion
- ✅ Parallel BM25 index fetching from GCS
- ✅ SimplifiedBM25 scorer with keyword boosting (1.5x for LLM keywords)
- ✅ Reciprocal Rank Fusion (RRF) algorithm
- ✅ Query endpoint routing: use_hybrid parameter (default: True)
- ✅ Unit tests: test_hybrid_search_logic.py (7 tests)
- ✅ E2E tests: test_05k_hybrid_search_keyword_boost
- ✅ Fixed metadata_filter → filters API parameter
- ✅ **All 69 tests passing** (38 e2e, 23 integration, 8 unit)

**Results:**
- ✅ Production-ready hybrid search system
- ✅ Best of both worlds: semantic (vector) + keyword (BM25)
- ✅ No external dependencies (Simplified BM25, no global IDF)
- ✅ Summary/keywords in search results (better UX)
- ✅ Cost-efficient: ~$0.000225/doc LLM extraction

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

## 🎓 Learning Resources

**Hybrid Search:**
- BM25: https://en.wikipedia.org/wiki/Okapi_BM25
- Reciprocal Rank Fusion: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

**PostgreSQL:**
- JSONB: https://www.postgresql.org/docs/current/datatype-json.html
- GIN Indexes: https://www.postgresql.org/docs/current/gin-intro.html
- Full-Text Search: https://www.postgresql.org/docs/current/textsearch.html

---

## 🔄 Version History

**v0.2.1 (Current - Dec 19, 2025):**
- ✅ Hybrid Search Phase 2 complete (BM25 index generation, LLM extraction)
- ✅ Metadata filtering implemented (MongoDB Query Language, filter_parser.py)
- ✅ Reranking implemented (gemini-2.5-flash-lite, configurable)
- ✅ All env vars required (no defaults in code)
- ✅ Models unified to gemini-2.5-flash-lite (extraction + reranking)
- ✅ BigQuery billing analytics tool (scripts/query_billing.py)
- ✅ 194 tests passing (134 unit, 23 integration, 37 e2e)

**v0.2.0 (Dec 11, 2025):**
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

**Option B: BigQuery Billing Analytics** (Cost Optimization)
- **Status:** Infrastructure ready, waiting for data (Dec 19-20)
- **Next:** Analyze costs when data arrives, optimize expensive operations
- **Tasks:**
  1. Query billing data (scripts/query_billing.py)
  2. Identify cost drivers (Gemini API, embeddings, storage)
  3. Create cost dashboard queries
  4. Optimize if needed

**Option C: Schema Migration System** (Infrastructure Improvement)
- **Effort:** 12-16 hours
- **Impact:** Production operations requirement
- **Value:** Versioned migrations, rollback capability, testable schema changes
- **Tasks:**
  1. Setup Alembic for PostgreSQL migrations
  2. Create migration for existing schema
  3. Implement GCS schema versioning
  4. Update deployment scripts

### 🗓️ Recommended Sequence:

1. **Today (Dec 19):** Wait for billing data → analyze costs
2. **Next session:** Choose Hybrid Search Phase 3 (2-3 hours) OR wait for billing data
3. **Future:** Schema Migration System when ready for production hardening

---

## 📝 Implementation Commands

**To implement Hybrid Search Phase 3:**
```
"Implement Hybrid Search Phase 3 from ROADMAP.md - BM25 query integration with RRF fusion"
```

**To analyze billing data:**
```
"Analyze BigQuery billing data - identify cost drivers and optimize"
```

**To implement Schema Migration System:**
```
"Implement Schema Migration System from ROADMAP.md - Alembic for PostgreSQL + GCS versioning"
```

---

**Status:** v0.2.1 - Metadata filtering, reranking, and hybrid search Phase 2 complete. Ready for Phase 3 or cost optimization.
