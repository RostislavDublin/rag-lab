# Hybrid Search Blueprint

**Status:** Phase 3 Complete (Query Integration)  
**Updated:** December 19, 2025  
**Feature:** Vector + BM25 + RRF Fusion + LLM Keywords

---

## Overview

Hybrid search combining:
- **Vector search** (semantic similarity, chunk-level) - top-100 retrieval
- **BM25 search** (keyword matching, document-level) - applied to vector results
- **RRF fusion** (Reciprocal Rank Fusion) - combines both rankings
- **LLM-generated keywords** (compensates missing IDF)

**Architecture:** Two-stage retrieval (Variant A)
- Stage 1: Vector search retrieves top-100 chunks (semantic filter)
- Stage 2: BM25 scoring on those 100 chunks (keyword relevance)
- Stage 3: RRF fusion combines both rankings
- Stage 4: Optional cross-encoder reranking

**Goal:** Improve retrieval quality by combining semantic and keyword signals without compromising architectural simplicity.

---

## LLM Model Selection (Dec 2025)

### Production Configuration

**Extraction (Phase 2):** `gemini-2.5-flash-lite`
- Cost: $0.10 input + $0.40 output per 1M tokens (~$0.000225/doc)
- Success rate: 100% (vs Flash 90%)
- Quality: Complete JSON with summary + keywords every time
- Total: $2.25 per 10K documents (4.2x cheaper than flash)

**Reranking (Phase 3):** `gemini-2.5-flash-lite`
- Same model as extraction (unified, reliable, cheap)
- Cost: $0.10 input + $0.40 output per 1M tokens
- 100% success rate, faster than flash

### Why Flash-Lite Won

**Testing (Dec 18, 2025):**
```
Model: gemini-2.5-flash
- Run 1-7, 9-10: SUCCESS (keywords: 15-21)
- Run 8: FAIL (unterminated string, invalid JSON)
- Success rate: 90%

Model: gemini-2.5-flash-lite  
- Run 1-10: SUCCESS (keywords: 20-26)
- Success rate: 100%
```

**Root cause:** Flash has unstable JSON generation on longer documents (>1500 chars)
- Missing closing braces
- Unterminated strings  
- Missing `keywords` field

**Solution:** Flash-lite is BOTH cheaper AND more reliable.

### Retry Logic

```python
# src/bm25/llm_extraction.py
MAX_RETRY_ATTEMPTS = 5          # Total attempts
RETRY_INITIAL_DELAY = 1.0       # 1 second
RETRY_EXP_BASE = 2.0            # Exponential: 1s, 2s, 4s, 8s, 16s
RETRY_STATUS_CODES = {429, 500, 503, 504}  # Rate limit + server errors

# Both JSON errors AND API errors are retriable
# (Flash unstable → retry can succeed on next attempt)
```

**Configuration:**
```bash
# .env.local
EMBEDDING_MODEL=text-embedding-005              # Vector embeddings
RERANKER_MODEL=gemini-2.5-flash-lite            # Search reranking (REQUIRED)
LLM_EXTRACTION_MODEL=gemini-2.5-flash-lite      # Summary/keywords (REQUIRED)
```

---

## Architecture

### Full System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          UPLOAD / INDEXING FLOW                          │
└──────────────────────────────────────────────────────────────────────────┘

Document Upload (PDF/TXT)
  ↓
┌─────────────────────────────────────────┐
│ STAGE 1: Text Extraction & Parsing     │
├─────────────────────────────────────────┤
│ PDF → pymupdf4llm (Markdown)            │
│ TXT → direct read                       │
│                                         │
│ Output: Full extracted text             │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 2: Chunking                       │
├─────────────────────────────────────────┤
│ Semantic chunking (512 tokens)          │
│ → chunks: [{text, index}, ...]          │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 3: LLM Summary & Keywords         │
├─────────────────────────────────────────┤
│ LLM: gemini-2.5-flash-lite              │
│ Input: Full document text               │
│ Retry: 5 attempts, exp backoff          │
│                                         │
│ Prompt: "Generate concise summary       │
│          (2-3 sentences) and extract    │
│          10-15 key terms..."            │
│                                         │
│ Output (JSON):                          │
│ - summary: "This document covers..."    │
│ - keywords: ["kubernetes", ...]         │
│                                         │
│ Cost: ~$0.000225/doc (flash-lite)       │
│ Success rate: 100%                      │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 4: Tokenization & BM25 Index     │
├─────────────────────────────────────────┤
│ Tokenize full text:                     │
│ → lowercase, remove punctuation         │
│ → ["kubernetes", "deployment", ...]     │
│                                         │
│ Count term frequencies:                 │
│ → {"kubernetes": 15, "deployment": 12}  │
│                                         │
│ Create bm25_doc_index.json:             │
│ {                                       │
│   "summary": "Document summary...",     │
│   "keywords": [...],                    │
│   "term_frequencies": {...},            │
│   "doc_length": 5000                    │
│ }                                       │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 5: Embedding Generation           │
├─────────────────────────────────────────┤
│ Model: text-embedding-005               │
│ Generate embedding per chunk:           │
│ → chunk[0] → [0.12, 0.45, ...] (768d)   │
│ → chunk[1] → [0.23, 0.67, ...]          │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 6: Dual Storage                   │
├─────────────────────────────────────────┤
│ PostgreSQL:                             │
│ → Embeddings (vector column)            │
│ → Metadata (filename, user, etc.)       │
│                                         │
│ GCS:                                    │
│ → {doc_uuid}/original                   │
│ → {doc_uuid}/extracted.txt              │
│ → {doc_uuid}/chunks/*.json              │
│ → {doc_uuid}/bm25_doc_index.json ← NEW! │
└─────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          SEARCH / RETRIEVAL FLOW                         │
└──────────────────────────────────────────────────────────────────────────┘

Query: "Kubernetes deployment strategies"
  ↓
┌─────────────────────────────────────────┐
│ STAGE 1: Query Embedding                │
├─────────────────────────────────────────┤
│ Model: text-embedding-005               │
│ Query → [0.34, 0.78, ...] (768d)        │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 2: Dual Retrieval                │
├─────────────────────────────────────────┤
│ A) Vector Search (chunk-level):         │
│    → PostgreSQL HNSW index              │
│    → Top-100 chunks (semantic)          │
│    → [{chunk_id, doc_uuid, sim}, ...]   │
│                                         │
│ B) BM25 Search (document-level):        │
│    → Extract unique doc_uuids           │
│    → Batch fetch bm25_doc_index.json    │
│    → Tokenize query                     │
│    → Score each document                │
│    → Map doc scores → chunks            │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 3: RRF Fusion                     │
├─────────────────────────────────────────┤
│ Rank by vector similarity:              │
│   [chunk_A, chunk_B, chunk_C, ...]      │
│                                         │
│ Rank by document BM25 score:            │
│   [chunk_C, chunk_A, chunk_D, ...]      │
│                                         │
│ RRF formula: score = Σ 1/(60 + rank)    │
│                                         │
│ → Top-10 chunks (best hybrid score)     │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│ STAGE 4: Cross-encoder Reranking        │
│         (already exists!)                │
├─────────────────────────────────────────┤
│ Fetch chunk texts from GCS              │
│ Rerank with cross-encoder               │
│ → Final top-10 results                  │
└─────────────────────────────────────────┘
```

### Why Chunk-level Vector + Document-level BM25?

**Vector on chunks:**
- ✅ Precision: finds specific relevant fragments
- ✅ Embedding quality: 500 words > 5000 words
- ✅ Granular retrieval: user gets exact passage

**BM25 on documents:**
- ✅ Context: keyword match across entire document
- ✅ Verification: "document is really about Kubernetes, not just a mention"
- ✅ Compact: 1 index per document vs N indexes per chunks
- ✅ Natural diversity: different documents = different topics

**Example:**

```
Vector results (chunks):
  - Chunk A3 (Doc A): similarity 0.85
  - Chunk B2 (Doc B): similarity 0.80
  
BM25 scores (documents):
  - Doc A: BM25 = 18.5 (много "kubernetes", "deployment")
  - Doc B: BM25 = 5.2 (мало keyword matches)
  
Mapped to chunks:
  - Chunk A3: vector=0.85, doc_bm25=18.5 ← HIGH combined score!
  - Chunk B2: vector=0.80, doc_bm25=5.2  ← Lower combined score
```

**Result:** Chunk A3 wins (high semantic similarity + document contains keywords!)

---

## Key Design Decisions

### 1. Simplified BM25 (NO global IDF)

**Decision:** Use BM25 without global IDF component.

**Formula:**
```python
SimpleBM25(term, doc) = (tf × (k1 + 1)) / (tf + k1 × (1 - b + b × dl/avgdl))

# Parameters:
k1 = 1.2      # Term frequency saturation
b = 0.75      # Length normalization strength
avgdl = 1000  # Average document length (constant approximation)
```

**What we keep:**
- ✅ Term frequency (TF)
- ✅ Length normalization (longer docs penalized)
- ✅ Saturation (diminishing returns for high TF)

**What we drop:**
- ❌ IDF (Inverse Document Frequency)

**Why no global IDF?**

Problem with global stats:
```python
# Race condition example:
Upload 1: reads total_docs = 100
Upload 2: reads total_docs = 100
Upload 1: writes total_docs = 101
Upload 2: writes total_docs = 101  ← BUG! Should be 102

# Partial failure:
document uploaded to GCS ✅
global stats update fails ❌
→ Inconsistent state!

# Scalability:
PostgreSQL row lock on bm25_global_stats
→ All uploads blocked!
```

**Alternative considered and rejected:**
- Background workers (eventual consistency, complexity)
- Cached stats (cold start issues, stale data)
- Per-document IDF (not true IDF, less useful)

**Conclusion:** 
- Simplified BM25 is reliable (no distributed state)
- Quality loss (~10-15%) acceptable when combined with vector search
- Vector search already filters semantically relevant documents

### 2. LLM Summary & Keywords Compensate Missing IDF

**Problem:** Without IDF, all words weighted equally.

**Solution:** LLM generates document summary (2-3 sentences) + extracts important terms at upload time.

**Approach:**

```python
# At upload time (async, non-blocking)
llm_metadata = await genai_client.models.generate_content(
    model="gemini-2.0-flash-lite",
    contents=f"""
    1. Generate concise summary (2-3 sentences) of this document
    2. Extract 10-15 most important keywords
    Include:
    - Technical terms and concepts
    - Key entities (products, technologies, names)
    - Important abbreviations and their expansions
    
    Document text:
    {full_text}
    
    Return JSON: {{
        "summary": "...",
        "keywords": ["term1", "term2", ...]
    }}
    """
)
```

**Cost:** ~$0.0004 per document (negligible, same single LLM call)

**Benefits:**
- **Summary:** Show to users in search results (better than first chunk preview)
- **Summary:** Provides document context without reading full text  
- **Keywords:** Used for BM25 1.5x boosting
- **Keywords:** LLM understands semantic importance (better than statistical IDF)

**Usage in BM25:**

```python
def enhanced_bm25(query_terms, doc_index):
    # 1. Base BM25 score
    score = simplified_bm25(query_terms, doc_index)
    
    # 2. Boost if query term is in LLM-extracted keywords
    boost_multiplier = 1.0
    for term in query_terms:
        if term in doc_index['keywords']:  # From LLM summary extraction
            boost_multiplier *= 1.5  # 50% boost
    
    return score * boost_multiplier
```

**Why this works:**
- **Summary benefits:**
  - Better user experience: meaningful preview instead of raw chunk text
  - Document context: user sees what document is about before clicking
  - No extra cost: generated in same LLM call as keywords
  - Searchable: can be indexed for future full-text search features
- **Keywords benefits:**
  - LLM understands semantic importance (better than statistical IDF)
  - Recognizes synonyms and related concepts
  - Captures domain-specific terminology
  - Understands context (e.g., "deployment" in DevOps vs general usage)

**Example:**

```
Document: "Guide to Kubernetes Rolling Updates and Blue-Green Deployments"

Statistical approach (missing IDF):
- "the" = weight 1.0
- "kubernetes" = weight 1.0
- "deployment" = weight 1.0
→ All words equal! ❌

LLM approach:
- LLM keywords: ["Kubernetes", "rolling updates", "blue-green deployment", "DevOps"]
- Query: "kubernetes deployment"
- Boost: 1.5 × 1.5 = 2.25x score
→ Important terms weighted higher! ✅
```

### 3. API Design: Parameter vs Separate Endpoint

**Decision:** Add `use_hybrid` parameter to existing `/v1/query` endpoint instead of creating `/v1/query/hybrid`.

**Rationale:**

```python
# ✅ CHOSEN: Parameter approach
POST /v1/query
{
  "query": "kubernetes deployment",
  "use_hybrid": true,  # or false
  "rerank": false
}

# ❌ REJECTED: Separate endpoint
POST /v1/query/hybrid  # Duplicate logic, harder to maintain
```

**Benefits:**
- ✅ Single endpoint for all search modes (vector, hybrid, future modes)
- ✅ Consistent API (similar to existing `rerank` parameter)
- ✅ Backward compatible (default `use_hybrid=True`)
- ✅ A/B testing via parameter (easier than different URLs)
- ✅ Less code duplication (90% logic shared)
- ✅ Room for future: can add convenience methods later if needed
  - Example: `POST /v1/query/semantic` → calls `/v1/query` with `use_hybrid=false`
  - Example: `POST /v1/query/keywords` → calls `/v1/query` with custom params

**When to use each mode:**

| Query Type | use_hybrid | Reason |
|------------|-----------|--------|
| "kubernetes rolling update" | `true` | Exact technical terms matter |
| "documents about ML" | `false` | Semantic similarity more important |
| "PostgreSQL pgvector" | `true` | Specific product names |
| "how to improve performance" | `false` | Conceptual, many synonyms |
| Long text snippet | `false` | Too many terms for BM25 |

**Default = True** because keyword verification improves RAG quality in most cases.

### 4. RRF (Reciprocal Rank Fusion)

**Formula:**
```python
RRF(chunk, k=60) = Σ 1/(k + rank_i(chunk))

# Where:
# - rank_i = rank of chunk in i-th ranking
# - k = 60 (standard constant, prevents divide-by-zero)
```

**Example:**

```
Vector ranking:  [A, B, C, D, E]
BM25 ranking:    [C, A, F, B, G]

RRF scores:
Chunk A: 1/(60+1) + 1/(60+2) = 0.0164 + 0.0161 = 0.0325
Chunk B: 1/(60+2) + 1/(60+4) = 0.0161 + 0.0156 = 0.0317
Chunk C: 1/(60+3) + 1/(60+1) = 0.0159 + 0.0164 = 0.0323

Final ranking: [A, C, B, ...]
```

**Why RRF?**
- ✅ No parameter tuning (unlike weighted average)
- ✅ Rank-based (works even if scores not comparable)
- ✅ Proven effective in information retrieval
- ✅ Simple to implement

---

## Data Structures

### GCS (single source of truth for content)

```
{doc_uuid}/
  ├── original                  # Original PDF/TXT file
  ├── extracted.txt             # Full extracted text (Markdown from pymupdf4llm)
  ├── chunks/
  │   ├── 000.json             # {"text": "chunk text", "index": 0}
  │   ├── 001.json
  │   └── ...
  └── bm25_doc_index.json      # ← NEW: Document-level BM25 index
```

### bm25_doc_index.json Schema (GCS)

**IMPORTANT: Only term frequencies stored in GCS!**

All other metadata (summary, keywords, token_count) is stored in PostgreSQL for fast access during vector search. This avoids extra GCS requests and simplifies the architecture.

```json
{
  "term_frequencies": {
    "kubernetes": 15,
    "deployment": 12,
    "strategy": 8,
    "rolling": 5,
    "update": 7,
    "container": 8,
    "orchestration": 6
  }
}
```

**Storage Split Rationale:**

**PostgreSQL** (fast, accessed during vector search):
- `summary TEXT` - document summary for UI display
- `keywords TEXT[]` - LLM-extracted keywords for 1.5x BM25 boost
- `token_count INTEGER` - document length for BM25 normalization

**GCS** (fetched only for hybrid search):
- `term_frequencies` - full TF map for BM25 scoring

**Why split?**
- Vector search already queries PostgreSQL → free metadata access
- GCS fetch only when hybrid search enabled → cost-effective
- Batch GCS fetching → efficient parallel retrieval

**Note:** 
- doc_uuid → implicit in file path `{doc_uuid}/bm25_doc_index.json`
- Only term frequencies stored in GCS (pure BM25 index data)

### PostgreSQL (МЕТАДАННЫЕ - summary и keywords!)

```sql
-- NEW: Add summary and keywords columns to original_documents
ALTER TABLE original_documents 
ADD COLUMN summary TEXT,
ADD COLUMN keywords TEXT[];  -- Array of keywords for filtering

-- Existing schema (NO changes to document_chunks)
CREATE TABLE original_documents (
    id SERIAL PRIMARY KEY,
    doc_uuid UUID UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}',
    summary TEXT,           -- NEW: LLM-generated summary (2-3 sentences)
    keywords TEXT[],        -- NEW: LLM-extracted keywords for boosting + filtering
    token_count INTEGER,    -- NEW: Document length in tokens (for BM25 normalization)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    original_doc_id INTEGER REFERENCES original_documents(id),
    embedding VECTOR(768) NOT NULL,
    chunk_index INTEGER NOT NULL
);

-- NEW: Index for keyword filtering
CREATE INDEX idx_documents_keywords 
ON original_documents USING GIN(keywords);
```

**Why summary/keywords in PostgreSQL:**
- ✅ Already fetched in vector search (no extra GCS request)
- ✅ Can filter by keywords: `WHERE 'Kubernetes' = ANY(keywords)`
- ✅ Summary ready to show in search results immediately
- ✅ Atomic updates with document metadata
- ✅ Can use existing filter_parser for keyword filtering

---

## Implementation Workflow

### Upload Workflow (modified)

```python
async def upload_document(file):
    # 1-5: Existing steps (unchanged)
    # 1. Extract text from PDF
    # 2. Chunk text (512 tokens each)
    # 3. Generate embeddings
    # 4. Save to PostgreSQL (embeddings)
    # 5. Save to GCS (original + extracted + chunks)
    
    # 6. NEW: Generate document-level BM25 index
    full_text = " ".join(chunk['text'] for chunk in chunks)
    
    # Tokenize entire document
    tokens = tokenize(full_text)  # lowercase, remove punctuation
    
    # Compute term frequencies
    term_freq = Counter(tokens)
    
    # 7. NEW: LLM summary + keyword extraction
    llm_metadata = await genai_client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=f"""
        1. Generate concise summary (2-3 sentences)
        2. Extract 10-15 most important keywords
        Return JSON: {{
            "summary": "...",
            "keywords": ["term1", "term2"]
        }}
        
        Document: {full_text[:8000]}  # First ~8K tokens
        """
    )
    
    llm_result = json.loads(llm_metadata.text)
    summary = llm_result['summary']
    keywords = llm_result['keywords']
    
    # 8. NEW: Create BM25 index (ONLY term frequencies!)
    bm25_index = {
        "term_frequencies": dict(term_freq)
    }
    
    # 9. NEW: Save to PostgreSQL (summary + keywords + token_count as document metadata)
    await db.execute(
        """
        UPDATE original_documents 
        SET summary = $1, keywords = $2, token_count = $3
        WHERE doc_uuid = $4
        """,
        summary, keywords, len(tokens), doc_uuid
    )
    
    # 10. NEW: Save BM25 index to GCS
    await gcs.upload(
        f"{doc_uuid}/bm25_doc_index.json",
        json.dumps(bm25_index)
    )
```

### Search Workflow (modified existing endpoint)

```python
class QueryRequest(BaseModel):
    """Request model for /v1/query endpoint."""
    query: str
    top_k: int = 10
    use_hybrid: bool = True           # NEW! Enable hybrid search (vector + BM25 + RRF)
    rerank: bool = False              # Existing: cross-encoder reranking
    min_similarity: float = 0.0       # Existing: vector similarity threshold
    filters: dict = None              # Existing: MongoDB-style metadata filters

@app.post("/v1/query")
async def query(request: QueryRequest):
    """
    Universal search endpoint.
    
    Modes:
    - use_hybrid=True: Vector + BM25 + RRF (default, best quality)
    - use_hybrid=False: Pure vector search (faster, semantic only)
    
    Both modes support optional cross-encoder reranking (rerank=True).
    """
    
    if request.use_hybrid:
        return await _hybrid_search(request)
    else:
        return await _vector_search(request)  # Existing implementation

async def _hybrid_search(request: QueryRequest):
    """Hybrid search implementation (vector + BM25 + RRF)."""
    
    # Step 1: Vector search (existing function)
    query_embedding = await genai_client.models.embed_content(
        model="text-embedding-005",
        contents=request.query
    )
    
    vector_results = await vector_db.search_similar_chunks(
        query_embedding=query_embedding.embeddings[0].values,
        top_k=100,  # Retrieve more for RRF
        min_similarity=request.min_similarity,
        filters=request.filters
    )
    # → [{chunk_id, doc_uuid, similarity, chunk_index, 
    #      summary, keywords, token_count, ...}, ...]  ← All metadata already here!
    
    # Step 2: Extract unique documents
    doc_uuids = list(set(r['doc_uuid'] for r in vector_results))
    
    # Step 3: Batch fetch BM25 indices from GCS (parallel)
    # Only term_frequencies needed - everything else already in vector_results!
    bm25_indices = await asyncio.gather(*[
        gcs.fetch_json(f"{uuid}/bm25_doc_index.json")
        for uuid in doc_uuids
    ])
    
    # Create lookup: doc_uuid → bm25_index
    bm25_lookup = {idx['doc_uuid']: idx for idx in bm25_indices}
    
    # Step 4: Compute BM25 scores for each document
    query_terms = tokenize(request.query)
    doc_bm25_scores = {}
    
    # Create lookup for metadata (token_count, keywords from PostgreSQL)
    doc_metadata = {r['doc_uuid']: r for r in vector_results}
    
    for doc_uuid, bm25_idx in bm25_lookup.items():
        metadata = doc_metadata[doc_uuid]
        score = enhanced_bm25(
            query_terms=query_terms,
            term_frequencies=bm25_idx['term_frequencies'],
            token_count=metadata['token_count'],  # From PostgreSQL
            keywords=metadata['keywords'],        # From PostgreSQL
            k1=1.2,
            b=0.75,
            avgdl=1000
        )
        doc_bm25_scores[doc_uuid] = score
    
    # Step 5: Map document BM25 scores to chunks
    for chunk in vector_results:
        chunk['doc_bm25_score'] = doc_bm25_scores[chunk['doc_uuid']]
    
    # Step 6: RRF Fusion
    # Ranking 1: by vector similarity
    vector_ranked = sorted(
        vector_results,
        key=lambda x: x['similarity'],
        reverse=True
    )
    
    # Ranking 2: by document BM25 score
    bm25_ranked = sorted(
        vector_results,
        key=lambda x: x['doc_bm25_score'],
        reverse=True
    )
    
    # Compute RRF scores
    rrf_scores = {}
    k = 60
    
    for rank, chunk in enumerate(vector_ranked, start=1):
        chunk_id = chunk['chunk_id']
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1/(k + rank)
    
    for rank, chunk in enumerate(bm25_ranked, start=1):
        chunk_id = chunk['chunk_id']
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1/(k + rank)
    
    # Step 7: Sort by RRF score and take top-k
    final_results = sorted(
        vector_results,
        key=lambda x: rrf_scores[x['chunk_id']],
        reverse=True
    )[:request.top_k]
    
    # Step 8: Add RRF scores to results (summary already present from vector search)
    for chunk in final_results:
        chunk['rrf_score'] = rrf_scores[chunk['chunk_id']]
        # chunk['summary'] and chunk['keywords'] already in result from PostgreSQL!
    
    # Step 9: Optional reranking (existing code)
    if request.rerank:
        final_results = await rerank_results(request.query, final_results)
    
    # Step 10: Fetch chunk texts from GCS (existing code)
    # ... existing chunk fetching logic ...
    
    return QueryResponse(
        query=request.query,
        results=final_results,
        total=len(final_results),
        search_mode="hybrid" if request.use_hybrid else "vector"
    )
```

### Example Response Structure

```json
{
  "query": "kubernetes deployment strategies",
  "search_mode": "hybrid",  // "hybrid" if use_hybrid=true, "vector" if false
  "total": 10,
  "results": [
    {
      "chunk_id": "chunk_abc_003",
      "doc_uuid": "abc-123-def-456",
      "chunk_index": 3,
      "document_summary": "This document covers Kubernetes deployment strategies including rolling updates, blue-green deployments, and canary releases. It discusses best practices for container orchestration and CI/CD integration.",
      "chunk_text": "Rolling updates in Kubernetes allow you to update deployments...",
      "similarity": 0.85,
      "doc_bm25_score": 18.5,
      "rrf_score": 0.0325,
      "metadata": {
        "filename": "k8s-deployment-guide.pdf",
        "upload_date": "2025-12-15"
      }
    },
    {
      "chunk_id": "chunk_def_002",
      "doc_uuid": "def-456-ghi-789",
      "chunk_index": 2,
      "document_summary": "Comprehensive guide to container orchestration patterns and microservices deployment on cloud platforms.",
      "chunk_text": "Blue-green deployment minimizes downtime by running two identical...",
      "similarity": 0.82,
      "doc_bm25_score": 12.3,
      "rrf_score": 0.0318,
      "metadata": {
        "filename": "cloud-deployment-patterns.pdf",
        "upload_date": "2025-12-14"
      }
    }
  ]
}
```

**Key fields:**
- `document_summary`: LLM-generated 2-3 sentence overview (shown to user as preview)
- `chunk_text`: Actual chunk content (full context)
- `rrf_score`: Hybrid ranking score (vector + BM25 fusion)
- `doc_bm25_score`: Document-level keyword relevance
- `similarity`: Chunk-level semantic similarity

**UI Display:**
```
📄 k8s-deployment-guide.pdf
   "This document covers Kubernetes deployment strategies including
    rolling updates, blue-green deployments..."
   
   Rolling updates in Kubernetes allow you to update deployments...
   
   Relevance: 0.85 | Keywords: High | Hybrid Score: 0.0325
```

---

## BM25 Implementation Details

### Tokenizer

```python
import re
from typing import List

def tokenize(text: str) -> List[str]:
    """
    Simple tokenizer for BM25.
    
    Steps:
    1. Lowercase
    2. Remove punctuation
    3. Split on whitespace
    4. Filter empty strings
    """
    # Lowercase
    text = text.lower()
    
    # Extract words (alphanumeric + hyphens)
    tokens = re.findall(r'\b[a-z0-9]+(?:-[a-z0-9]+)*\b', text)
    
    return tokens

# Example:
# tokenize("Kubernetes-based deployment strategies!")
# → ["kubernetes-based", "deployment", "strategies"]
```

**Note:** Can be enhanced later with:
- Stopwords removal (optional)
- Stemming (optional)
- Language detection (if multi-language support needed)

### BM25 Scorer

```python
from typing import List, Dict
from collections import Counter

class SimplifiedBM25:
    """
    Simplified BM25 without global IDF.
    Uses LLM keywords for term importance.
    """
    
    def __init__(self, k1: float = 1.2, b: float = 0.75, avgdl: float = 1000):
        self.k1 = k1
        self.b = b
        self.avgdl = avgdl
    
    def score(
        self,
        query_terms: List[str],
        doc_term_frequencies: Dict[str, int],
        token_count: int,
        keywords: List[str] = None
    ) -> float:
        """
        Compute simplified BM25 score.
        
        Args:
            query_terms: Tokenized query
            doc_term_frequencies: {term: count} for document
            token_count: Total number of tokens in document
            keywords: LLM-extracted important keywords (from summary generation)
        
        Returns:
            BM25 score (higher = more relevant)
        """
        score = 0.0
        
        for term in query_terms:
            # Get term frequency in document
            tf = doc_term_frequencies.get(term, 0)
            
            if tf == 0:
                continue
            
            # BM25 formula (without IDF component)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * (token_count / self.avgdl)
            )
            
            score += numerator / denominator
        
        # Keyword boosting
        if keywords:
            boost = 1.0
            for term in query_terms:
                # Case-insensitive matching
                if any(term.lower() in kw.lower() for kw in keywords):
                    boost *= 1.5
            score *= boost
        
        return score

# Usage:
bm25 = SimplifiedBM25()
score = bm25.score(
    query_terms=["kubernetes", "deployment"],
    doc_term_frequencies={"kubernetes": 15, "deployment": 12, "pod": 8},
    token_count=5000,
    keywords=["Kubernetes", "deployment strategies", "DevOps"]
)
```

### RRF Fusion

```python
from typing import List, Dict

def reciprocal_rank_fusion(
    rankings: List[List[Dict]],
    k: int = 60
) -> List[Dict]:
    """
    Combine multiple rankings using Reciprocal Rank Fusion.
    
    Args:
        rankings: List of ranked result lists
            Each ranking is a list of dicts with 'chunk_id' key
        k: RRF constant (default: 60)
    
    Returns:
        Combined ranking sorted by RRF score
    """
    rrf_scores = {}
    
    # Process each ranking
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            chunk_id = item['chunk_id']
            rrf_score = 1.0 / (k + rank)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + rrf_score
    
    # Get all unique items
    all_items = {}
    for ranking in rankings:
        for item in ranking:
            all_items[item['chunk_id']] = item
    
    # Sort by RRF score
    sorted_items = sorted(
        all_items.values(),
        key=lambda x: rrf_scores[x['chunk_id']],
        reverse=True
    )
    
    # Add RRF scores to results
    for item in sorted_items:
        item['rrf_score'] = rrf_scores[item['chunk_id']]
    
    return sorted_items

# Usage:
vector_ranking = [
    {'chunk_id': 1, 'similarity': 0.85},
    {'chunk_id': 2, 'similarity': 0.80},
    {'chunk_id': 3, 'similarity': 0.75}
]

bm25_ranking = [
    {'chunk_id': 3, 'bm25': 15.2},
    {'chunk_id': 1, 'bm25': 12.8},
    {'chunk_id': 5, 'bm25': 10.1}
]

fused = reciprocal_rank_fusion([vector_ranking, bm25_ranking])
# → Chunks ranked by combined RRF score
```

---

## Implementation Plan

### Phase 1: Core BM25 Module

**Files to create:**
- `src/bm25/__init__.py`
- `src/bm25/tokenizer.py` - Tokenization logic
- `src/bm25/scorer.py` - SimplifiedBM25 class
- `src/bm25/fusion.py` - RRF implementation

**Tasks:**
1. Implement tokenizer with tests
2. Implement BM25 scorer with tests
3. Implement RRF fusion with tests
4. Unit tests for edge cases

**Estimated effort:** 4-6 hours

### Phase 2: Upload Integration

**Files to modify:**
- `src/database.py` - Add summary/keywords columns via migration
- `src/main.py` - Add BM25 index generation on upload
- `src/storage.py` - Add bm25_doc_index.json upload

**Tasks:**
1. **Database migration:**
   ```sql
   ALTER TABLE original_documents 
   ADD COLUMN summary TEXT,
   ADD COLUMN keywords TEXT[],
   ADD COLUMN token_count INTEGER;
   
   CREATE INDEX idx_documents_keywords 
   ON original_documents USING GIN(keywords);
   ```
2. Generate term frequencies on upload
3. Call LLM for summary + keyword extraction (async, single call)
   - Generate 2-3 sentence summary
   - Extract 10-15 important keywords
   - Both in one LLM request (~$0.0004 per doc)
4. Save summary + keywords + token_count to PostgreSQL (UPDATE original_documents)
5. Create bm25_doc_index.json structure (ONLY term_frequencies!)
6. Upload bm25_doc_index.json to GCS alongside chunks
7. Handle errors gracefully (LLM failures shouldn't block upload)
8. **Update filter_parser.py:**
   - Add "summary", "keywords", "token_count" to COLUMN_FIELDS
   - Test: `{"filters": {"keywords": {"$in": ["Kubernetes"]}}}`
   - Test: `{"filters": {"token_count": {"$gte": 1000}}}`  # Long docs only

**Estimated effort:** 4-5 hours (includes migration)
5. Create bm25_doc_index.json structure (only term_frequencies, doc_length)
6. Upload bm25_doc_index.json to GCS alongside chunks
7. Handle errors gracefully (LLM failures shouldn't block upload)
8. **Verify filter_parser compatibility:**
   - Add "summary" and "keywords" to COLUMN_FIELDS in filter_parser.py
   - Test: `{"filters": {"keywords": {"$in": ["Kubernetes"]}}}`

**Estimated effort:** 4-5 hours (includes migration)

### Phase 3: Hybrid Search Integration

**Files to modify:**
- `src/models.py` - Add `use_hybrid` field to existing QueryRequest
- `src/main.py` - Modify `/v1/query` endpoint to support hybrid mode

**Tasks:**
1. Add `use_hybrid: bool = True` to QueryRequest model
2. Add `search_mode: str` to QueryResponse model
3. Refactor existing vector search into `_vector_search()` function
4. Implement new `_hybrid_search()` function:
   - Batch fetch BM25 indices from GCS
   - Compute BM25 scores
   - RRF fusion
5. Update `/v1/query` endpoint to route based on `use_hybrid`
6. Ensure existing reranking works with both modes

**Estimated effort:** 4-5 hours

### Phase 4: Testing

**Files to create:**
- `tests/unit/test_bm25_tokenizer.py`
- `tests/unit/test_bm25_scorer.py`
- `tests/unit/test_rrf_fusion.py`
- `tests/e2e/test_hybrid_search.py`

**Test scenarios:**
1. Unit tests for BM25 components
2. E2E test: upload document → hybrid search → verify summary in response
3. Comparison: pure vector vs hybrid quality
4. Edge cases: empty documents, no keywords, LLM failure
5. Summary quality: verify LLM generates 2-3 sentence summaries
6. Performance benchmarks

**Estimated effort:** 6-8 hours

### Phase 5: Documentation

**Files to create/modify:**
- `docs/api.md` - Document `/v1/query/hybrid` endpoint
- `README.md` - Add hybrid search to features
- `docs/hybrid-search.md` - This document (update with learnings)

**Tasks:**
1. API documentation with examples
2. Update README features section
3. Add hybrid search to architecture diagram
4. Document tuning parameters (k1, b, RRF k)

**Estimated effort:** 2-3 hours

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_bm25_scorer.py

def test_bm25_term_frequency():
    """Higher TF should give higher score"""
    scorer = SimplifiedBM25()
    
    score_low = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 2},
        doc_length=1000
    )
    
    score_high = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 10},
        doc_length=1000
    )
    
    assert score_high > score_low

def test_bm25_length_normalization():
    """Longer documents should be penalized"""
    scorer = SimplifiedBM25()
    
    score_short = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 5},
        doc_length=500
    )
    
    score_long = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 5},
        doc_length=2000
    )
    
    assert score_short > score_long

def test_keyword_boosting():
    """LLM keywords should boost score"""
    scorer = SimplifiedBM25()
    
    score_no_boost = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 5},
        doc_length=1000,
        llm_keywords=[]
    )
    
    score_with_boost = scorer.score(
        query_terms=["kubernetes"],
        doc_term_frequencies={"kubernetes": 5},
        doc_length=1000,
        llm_keywords=["Kubernetes", "DevOps"]
    )
    
    assert score_with_boost > score_no_boost
```

### E2E Tests

```python
# tests/e2e/test_hybrid_search.py

@pytest.mark.asyncio
async def test_hybrid_search_keyword_trap():
    """
    Hybrid search should catch keyword-dependent queries
    where pure vector search fails.
    """
    # Upload document about Kubernetes
    kubernetes_doc = """
    Kubernetes Deployment Strategies
    
    This guide covers rolling updates, blue-green deployments,
    and canary releases in Kubernetes environments.
    """
    
    # Upload document about Docker (semantically similar but wrong topic)
    docker_doc = """
    Docker Container Management
    
    Learn how to manage containers, create images,
    and orchestrate multi-container applications.
    """
    
    await upload_document("k8s.txt", kubernetes_doc)
    await upload_document("docker.txt", docker_doc)
    
    # Query specifically for Kubernetes
    query = "Kubernetes deployment strategies"
    
    # Pure vector search might rank both similarly (both about containers)
    vector_results = await vector_search(query, top_k=2)
    
    # Hybrid search should rank Kubernetes doc higher (has keyword "Kubernetes")
    hybrid_results = await hybrid_search(query, top_k=2)
    
    # Assert hybrid search prioritizes Kubernetes doc
    assert "kubernetes" in hybrid_results[0]['filename'].lower()
```

---

## Performance Considerations

### GCS Fetch Optimization

**Current:**
```python
# Fetch BM25 indices for N documents
bm25_indices = await asyncio.gather(*[
    gcs.fetch(f"{uuid}/bm25_doc_index.json")
    for uuid in doc_uuids  # e.g., 10 documents
])
```

**Typical numbers:**
- Vector search returns ~100 chunks
- From ~10-20 unique documents
- 10-20 GCS requests (parallel)
- Each ~1-5KB (small files)
- Total latency: ~50-100ms

**Acceptable!** This is already optimized.

### Caching Consideration (future)

If BM25 fetch becomes bottleneck:
```python
# Optional: Cache BM25 indices in Redis
cache_key = f"bm25:{doc_uuid}"
bm25_idx = await redis.get(cache_key)

if not bm25_idx:
    bm25_idx = await gcs.fetch(f"{doc_uuid}/bm25_doc_index.json")
    await redis.set(cache_key, bm25_idx, ttl=3600)  # 1 hour
```

**For now:** Skip caching. Add only if profiling shows it's needed.

---

## Tuning Parameters

### BM25 Parameters

```python
k1 = 1.2   # Term frequency saturation
           # Higher = more weight to term frequency
           # Range: 1.2 - 2.0
           # Default: 1.2 (standard)

b = 0.75   # Length normalization
           # Higher = more penalty for long documents
           # Range: 0.0 - 1.0
           # Default: 0.75 (standard)

avgdl = 1000  # Average document length
              # Approximation constant
              # Tune based on your corpus
```

**How to tune:**
1. Start with defaults (k1=1.2, b=0.75)
2. Run evaluation on test queries
3. Adjust k1 if needed (higher if term frequency very important)
4. Adjust b if needed (lower if document length varies a lot)

### RRF Parameter

```python
k = 60  # RRF constant
        # Standard value from literature
        # DO NOT CHANGE unless you have strong reason
```

### Keyword Boost

```python
boost_multiplier = 1.5  # 50% boost per matched keyword
                        # Range: 1.2 - 2.0
                        # Tune based on evaluation
```

---

## Future Enhancements

### Short-term (if needed)

1. **Convenience endpoints** - Simplified APIs for common use cases
   - `POST /v1/query/semantic` → `use_hybrid=false` (pure vector)
   - `POST /v1/query/keywords` → `use_hybrid=true` with strict BM25 weighting
   - Smaller API surface for clients who don't need flexibility
2. **Stopwords removal** - Filter common words before BM25
3. **Stemming** - "deployment" = "deploy" = "deployed"
4. **Multi-language support** - Detect language, use appropriate tokenizer
5. **Query expansion** - Use LLM to expand query with synonyms

### Medium-term

1. **A/B testing framework** - Compare hybrid vs pure vector
2. **Analytics** - Track which signal (vector/BM25) contributes more
3. **Adaptive boosting** - Learn optimal keyword boost from feedback
4. **Document clustering** - Group similar documents for diversity

### Long-term

1. **Full BM25 with cached IDF** - If quality improvement justified
2. **Learning to rank** - Train model to combine signals optimally
3. **Query understanding** - Classify query intent (factual/exploratory/etc.)

---

## Success Metrics

### Quantitative

- **Retrieval quality:** MRR (Mean Reciprocal Rank) on evaluation set
- **Latency:** P50, P95, P99 for hybrid search endpoint
- **Cost:** LLM keyword extraction cost per document

### Qualitative

- **Keyword-dependent queries:** Improved recall for specific term searches
- **False positive reduction:** Fewer semantically similar but topically wrong results
- **User feedback:** Thumbs up/down on search results

### Target Metrics

```
Baseline (pure vector):
- MRR: 0.65
- P95 latency: 150ms
- Cost: $0

Hybrid search:
- MRR: >0.75 (15% improvement target)
- P95 latency: <250ms (100ms overhead acceptable)
- Cost: +$0.0004 per document (negligible)
```

---

## Risks & Mitigations

### Risk 1: LLM keyword extraction fails

**Impact:** No keyword boosting, falls back to base BM25

**Mitigation:**
```python
try:
    keywords = await llm.extract_keywords(text)
except Exception as e:
    logger.warning(f"LLM keyword extraction failed: {e}")
    keywords = []  # Graceful degradation
```

### Risk 2: GCS latency spikes

**Impact:** Slow hybrid search

**Mitigation:**
- Parallel fetch (already implemented)
- Monitor P95 latency
- Add caching if needed (Redis)

### Risk 3: BM25 quality not as good as expected

**Impact:** Hybrid search doesn't improve over pure vector

**Mitigation:**
- A/B testing framework
- Collect user feedback
- Iterate on parameters (k1, b, boost)
- Can always fall back to pure vector

### Risk 4: Token limit for LLM keyword extraction

**Impact:** Large documents truncated

**Mitigation:**
```python
# Only use first N tokens for keyword extraction
max_tokens = 8000  # ~6000 words
text_for_llm = full_text[:max_tokens]
```

This is acceptable - important keywords usually in beginning.

---

## API Usage Examples

### Hybrid Search (Default)

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{
    "query": "kubernetes deployment strategies",
    "top_k": 5,
    "use_hybrid": true
  }'
```

**Response includes both vector and BM25 signals:**
```json
{
  "query": "kubernetes deployment strategies",
  "total": 5,
  "results": [
    {
      "chunk_text": "Kubernetes supports multiple deployment strategies...",
      "similarity": 0.87,
      "filename": "k8s-guide.pdf",
      "chunk_index": 12,
      "doc_uuid": "abc-123",
      "doc_metadata": {
        "tags": ["devops", "kubernetes"]
      }
    }
  ]
}
```

**Note:** BM25 scores used internally for RRF fusion, not returned in API response.

### Pure Vector Search (Fallback)

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{
    "query": "kubernetes deployment strategies",
    "top_k": 5,
    "use_hybrid": false
  }'
```

**When to use pure vector:**
- Debugging hybrid search
- Comparing retrieval quality
- A/B testing

### Hybrid Search + Metadata Filters

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{
    "query": "deployment best practices",
    "top_k": 5,
    "use_hybrid": true,
    "filters": {
      "doc_metadata.tags": {"$in": ["kubernetes", "docker"]},
      "doc_metadata.user_id": "user123"
    }
  }'
```

**Architecture:** Metadata filtering applied during vector search (Stage 1), BM25 scoring only on filtered results.

### Hybrid Search + Reranking

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{
    "query": "how to rollback deployments",
    "top_k": 3,
    "use_hybrid": true,
    "rerank": true,
    "rerank_candidates": 10
  }'
```

**Full pipeline:**
1. Vector search → top-100 chunks
2. BM25 scoring → keyword boost
3. RRF fusion → combined ranking
4. Select top-10 candidates
5. Cross-encoder rerank → final top-3

**Response includes rerank scores:**
```json
{
  "results": [
    {
      "chunk_text": "To rollback a deployment in Kubernetes...",
      "similarity": 0.82,
      "rerank_score": 0.95,
      "rerank_reasoning": "Directly answers rollback procedure with kubectl commands",
      "filename": "k8s-ops.pdf"
    }
  ]
}
```

---

## References

### BM25
- [Okapi BM25 - Wikipedia](https://en.wikipedia.org/wiki/Okapi_BM25)
- [BM25 - The Next Generation of Lucene Relevance](https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables)

### RRF
- [Reciprocal Rank Fusion - Original Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [RRF in Modern Search Systems](https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)

### RAG Best Practices
- [Advanced RAG Techniques](https://arxiv.org/abs/2312.10997)
- [Multi-representation Indexing](https://arxiv.org/abs/2401.18059)

---

## Changelog

- **2025-12-16:** Initial blueprint created
- Document describes design decisions, architecture, implementation plan
- Ready for implementation Phase 1

---

## Approval & Next Steps

**Status:** ✅ Design approved, ready for implementation

**Next:** Create Phase 1 - Core BM25 Module

**Questions/concerns:** Document in GitHub issues

