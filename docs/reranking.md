# Reranking Configuration Guide

## Overview

Reranking is a **two-stage retrieval technique** where:
1. **Stage 1 (Fast Retrieval)**: Bi-encoder retrieves ~10-100 candidates based on semantic similarity
2. **Stage 2 (Precision Reranking)**: Reranker assesses each candidate's relevance to the query

This multi-stage approach is **recommended by Google** for production RAG systems to achieve higher quality results.

Reference: [Google Cloud: Multi-Stage Retrieval Systems](https://cloud.google.com/blog/products/ai-machine-learning/scaling-deep-retrieval-tensorflow-two-towers-architecture)

---

## Supported Reranking Methods

### 1. **Gemini LLM Reranking** (Default, Recommended)

Uses Gemini models to evaluate relevance - Google's recommended approach for high-quality reranking.

**Pros:**
- ✅ Highest quality - understands context deeply
- ✅ Works well with any query/document type
- ✅ No model downloads needed
- ✅ Recommended by Google's LlamaIndex RAG example

**Cons:**
- ❌ Slower (~7-8s for 20 documents with batching, ~500ms per 5 documents)
- ❌ Costs API tokens
- ❌ Requires GCP credentials

**Performance Optimization:**
- Uses async batching: splits documents into small batches (default: 2 docs/batch)
- Runs up to 10 batches in parallel via asyncio.Semaphore
- Example: 20 documents = 10 parallel batches × 2 docs = ~7-8s total
- Configurable via `GEMINI_RERANK_BATCH_SIZE` and `GEMINI_RERANK_MAX_CONCURRENT`

**Configuration:**
```bash
RERANKER_ENABLED=true
RERANKER_TYPE=gemini
RERANKER_MODEL=gemini-2.0-flash-exp  # or gemini-1.5-flash, gemini-2.5-flash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Optional: Batch configuration (advanced)
GEMINI_RERANK_BATCH_SIZE=2  # Documents per API call (default: 2)
GEMINI_RERANK_MAX_CONCURRENT=10  # Max parallel batches (default: 10)
```

**Example:**
```python
# Uses Gemini to assess relevance (0-10 scale) for each document
# Query: "What are our data retention policies?"
# Doc 1: "GDPR compliance report..." → Score: 9.5/10
# Doc 2: "Business metrics..." → Score: 2.1/10
```

---

### 2. **Local Cross-Encoder** (Fast, Offline)

Uses HuggingFace cross-encoder models that run locally on CPU/GPU.

**Pros:**
- ✅ Fast (~100ms per 5 documents)
- ✅ No API costs
- ✅ Works offline
- ✅ Privacy-friendly (no data leaves your server)

**Cons:**
- ❌ Lower quality than Gemini
- ❌ Model download required (120MB-1.4GB)
- ❌ May not improve over Google's text-embedding-005 bi-encoder

**Configuration:**
```bash
RERANKER_ENABLED=true
RERANKER_TYPE=local
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2  # 120MB, fast
# or
RERANKER_MODEL=BAAI/bge-reranker-base  # 1.1GB, better quality
# or
RERANKER_MODEL=BAAI/bge-reranker-large  # 1.4GB, best quality
```

**Available Models:**

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| `cross-encoder/ms-marco-MiniLM-L-12-v2` | 120MB | Fast | Good | Quick reranking |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | 90MB | Faster | Good | Very fast reranking |
| `BAAI/bge-reranker-base` | 1.1GB | Medium | Better | Balanced quality/speed |
| `BAAI/bge-reranker-large` | 1.4GB | Slow | Best | Maximum quality |

**Note:** With Google's text-embedding-005 bi-encoder, cross-encoder reranking may not provide significant improvements. Consider using Gemini LLM reranking instead.

---

### 3. **Cohere Rerank API**

Uses Cohere's proprietary reranking API.

**Pros:**
- ✅ High quality
- ✅ No model downloads
- ✅ Fast API

**Cons:**
- ❌ Requires Cohere API key
- ❌ API costs
- ❌ Third-party dependency

**Configuration:**
```bash
RERANKER_ENABLED=true
RERANKER_TYPE=cohere
RERANKER_MODEL=rerank-english-v3.0
COHERE_API_KEY=your-api-key-here
```

---

## Switching Between Implementations

### Using Docker Compose

Edit `docker-compose.yaml`:

```yaml
services:
  api:
    environment:
      # Option 1: Gemini LLM (default, recommended)
      RERANKER_ENABLED: "true"
      RERANKER_TYPE: "gemini"
      RERANKER_MODEL: "gemini-2.0-flash-exp"
      
      # Option 2: Local cross-encoder (fast, offline)
      # RERANKER_ENABLED: "true"
      # RERANKER_TYPE: "local"
      # RERANKER_MODEL: "cross-encoder/ms-marco-MiniLM-L-12-v2"
      
      # Option 3: Cohere API
      # RERANKER_ENABLED: "true"
      # RERANKER_TYPE: "cohere"
      # RERANKER_MODEL: "rerank-english-v3.0"
      # COHERE_API_KEY: "your-key"
      
      # Disable reranking
      # RERANKER_ENABLED: "false"
```

### Using .env File

Create `.env`:

```bash
# Gemini LLM reranking (recommended)
RERANKER_ENABLED=true
RERANKER_TYPE=gemini
RERANKER_MODEL=gemini-2.0-flash-exp
GOOGLE_CLOUD_PROJECT=myai-475419
GOOGLE_CLOUD_LOCATION=us-central1
```

### Programmatically

```python
import os

# Set before importing reranking factory
os.environ["RERANKER_ENABLED"] = "true"
os.environ["RERANKER_TYPE"] = "gemini"
os.environ["RERANKER_MODEL"] = "gemini-2.0-flash-exp"

from src.reranking.factory import RerankingFactory

reranker = RerankingFactory.create()
```

---

## When to Use Reranking

### ✅ Use Reranking When:
- You need **maximum precision** (legal, medical, compliance use cases)
- Queries are **complex or ambiguous**
- You have **keyword confusion** (e.g., "data" means different things in different contexts)
- You want to **improve top-3 results** quality

### ❌ Skip Reranking When:
- Bi-encoder already gives excellent results
- **Latency is critical** (<100ms requirements)
- **Cost optimization** is priority
- Simple keyword queries (consider hybrid search instead)

---

## Performance Comparison

Based on our E2E tests with Google's text-embedding-005 bi-encoder:

| Scenario | Bi-encoder (Stage 1) | + Cross-Encoder | + Gemini LLM |
|----------|---------------------|-----------------|--------------|
| Simple queries | Excellent (#1 correct) | No improvement | Slight improvement |
| Keyword confusion | Good (#1-3 correct) | Sometimes worse | Better context understanding |
| Latency (5 docs) | ~50ms | +100ms | +500ms |
| Cost per query | Free (self-hosted) | Free | ~$0.001 |

**Recommendation:** Use **Gemini LLM reranking** for production systems where quality > speed/cost.

---

## Alternative: Hybrid Search

Instead of reranking, consider **Hybrid Search** (vector + keyword search):

```bash
# Combines text-embedding-005 (semantic) + BM25 (keyword) + RRF fusion
# No ML model needed for reranking, fast and effective
```

This is Google's recommended approach for many use cases. See `docs/hybrid-search.md` for details.

---

## Troubleshooting

### Gemini Reranking Errors

**Error: "GCP project ID required"**
```bash
# Set environment variable
export GOOGLE_CLOUD_PROJECT=your-project-id

# Or pass to factory
reranker = GeminiReranker(project_id="your-project-id")
```

**Error: "Permission denied"**
```bash
# Ensure Application Default Credentials are set
gcloud auth application-default login

# Or use service account
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### Local Cross-Encoder Errors

**Error: "Model download failed"**
```bash
# Pre-download model
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')"
```

**Error: "CUDA out of memory"**
```bash
# Force CPU usage (slower but works)
export CUDA_VISIBLE_DEVICES=-1
```

---

## Implementation Details

### Architecture

```
src/reranking/
├── base.py          # Abstract interface (BaseReranker)
├── gemini.py        # Gemini LLM implementation (new, default)
├── local.py         # Cross-encoder implementation
├── cohere.py        # Cohere API implementation
└── factory.py       # Factory pattern (creates based on config)
```

### API Response

Reranking adds `rerank_score` and `rerank_reasoning` fields to query results:

```json
{
  "results": [
    {
      "chunk_id": 123,
      "filename": "gdpr_compliance.xml",
      "similarity": 0.85,
      "rerank_score": 0.95,  // Normalized 0-1 score (added when reranking enabled)
      "rerank_reasoning": "Document directly addresses GDPR compliance requirements"  // LLM explanation
    }
  ]
}
```

**Note:** `rerank_reasoning` is only available with Gemini reranking. Local cross-encoder and Cohere rerankers do not provide reasoning.

---

## References

- [Google Cloud: Multi-Stage Retrieval Systems](https://cloud.google.com/blog/products/ai-machine-learning/scaling-deep-retrieval-tensorflow-two-towers-architecture)
- [Google's LlamaIndex RAG Example (uses Gemini reranking)](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/sample-apps/llamaindex-rag)
- [HuggingFace Cross-Encoder Models](https://huggingface.co/cross-encoder)
- [MS MARCO: Microsoft Machine Reading Comprehension Dataset](https://microsoft.github.io/msmarco/)
