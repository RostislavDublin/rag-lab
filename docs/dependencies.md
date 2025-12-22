# Dependencies Architecture

## Overview

RAG Lab uses modular dependency management that aligns with the factory pattern architecture for embedding and reranking providers. Dependencies are split into base (required) and optional (provider-specific) files.

## File Structure

```
requirements-base.txt      # Core dependencies (always needed)
requirements-optional.txt  # Optional provider implementations  
requirements.txt           # Convenience file (includes base + optional)
```

## Design Principles

### 1. Provider Independence

The application uses factory patterns to select providers at runtime:

```python
# Factory selects implementation based on env config
if embedding_provider == "vertex_ai":
    # Uses google-genai SDK (in requirements-base.txt)
elif embedding_provider == "sentence_transformers":
    # Uses sentence-transformers (in requirements-optional.txt)
```

### 2. Pay Only for What You Use

**Problem:** Why include 150MB torch dependency if using only Vertex AI?

**Solution:** Split dependencies by provider:
- Base: Required for all deployments
- Optional: Only when using specific providers

### 3. Production Optimization

Production Dockerfile installs only `requirements-base.txt`:
- Faster builds: 5 min vs 10 min
- Smaller images: 400MB vs 550MB
- No unused dependencies

## Files

### requirements-base.txt

**Purpose:** Core dependencies required regardless of provider choice

**Contents:**
- FastAPI + uvicorn (web framework)
- PostgreSQL + pgvector (vector storage)
- Google Gen AI SDK (Vertex AI providers)
- PyJWT + cryptography (authentication)
- Document processing (pymupdf, pyyaml, xmltodict)
- Utilities (python-dotenv, tqdm, nltk)

**Size:** ~150MB installed

**When to use:**
- Production deployments (Vertex AI only)
- CI/CD pipelines
- Container images

### requirements-optional.txt

**Purpose:** Optional provider implementations

**Contents:**
- sentence-transformers (on-premise embeddings)
- torch (required by sentence-transformers, CPU-only in Docker)

**Size:** ~150MB installed

**When to use:**
- On-premise deployments (no cloud dependencies)
- Local development with all providers
- Vendor-independent configurations

### requirements.txt

**Purpose:** Convenience file for local development

**Contents:**
```txt
-r requirements-base.txt
-r requirements-optional.txt
```

**When to use:**
- Local development (try all providers)
- Testing different configurations
- Development environments

## Installation Scenarios

### Local Development (All Providers)

```bash
pip install -r requirements.txt
```

**Includes:** Vertex AI + sentence-transformers  
**Use case:** Development, testing all features  
**Size:** ~300MB

### Production (Vertex AI Only)

```bash
pip install -r requirements-base.txt
```

**Includes:** Only Vertex AI providers  
**Use case:** Cloud Run deployment  
**Size:** ~150MB

### On-Premise (No Cloud)

```bash
pip install -r requirements-base.txt -r requirements-optional.txt
```

**Includes:** sentence-transformers (no GCP dependencies)  
**Use case:** Air-gapped environments  
**Size:** ~300MB

## Docker Build Configuration

### Production (Default)

```dockerfile
# Dockerfile (default configuration)
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt
```

**Result:**
- Build time: ~5 minutes (first), ~30 seconds (cached)
- Image size: ~400MB
- Providers: Vertex AI only

### With Optional Providers

```dockerfile
# Uncomment in Dockerfile for on-premise providers
COPY requirements-optional.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements-optional.txt
```

**Result:**
- Build time: ~10 minutes (first), ~30 seconds (cached)
- Image size: ~550MB
- Providers: Vertex AI + sentence-transformers

**Note:** torch installed separately from PyTorch CPU-only index to avoid CUDA libraries (saves 3GB).

## Provider Configuration

### Vertex AI (Default)

```bash
# .env configuration
EMBEDDING_PROVIDER=vertex_ai
EMBEDDING_MODEL=text-embedding-005
RERANKING_PROVIDER=vertex_ai
```

**Requirements:** `requirements-base.txt` only  
**API Costs:** $0.025 per 1M tokens (embeddings), $3 per 1M tokens (reranking)

### On-Premise (sentence-transformers)

```bash
# .env configuration
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
RERANKING_PROVIDER=local
RERANKING_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

**Requirements:** `requirements-base.txt` + `requirements-optional.txt`  
**API Costs:** $0 (runs locally)

## Build Time Comparison

| Configuration | First Build | Cached Build | Image Size |
|--------------|-------------|--------------|------------|
| Base only | 5 minutes | 30 seconds | 400MB |
| Base + Optional | 10 minutes | 30 seconds | 550MB |
| Base + torch+CUDA | 20 minutes | 30 seconds | 4GB |

**Caching:** Docker layer caching works for both configurations. Code-only changes rebuild in ~30 seconds.

## Migration Guide

### From Monolithic requirements.txt

**Before:**
```txt
# All dependencies in one file
google-genai>=0.3.0
sentence-transformers>=2.3.0
torch>=2.0.0
...
```

**After:**
```txt
# requirements-base.txt
google-genai>=0.3.0
...

# requirements-optional.txt
sentence-transformers>=2.3.0
torch>=2.0.0

# requirements.txt
-r requirements-base.txt
-r requirements-optional.txt
```

### Update Docker

**Before:**
```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
```

**After:**
```dockerfile
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# Optional: Uncomment for on-premise providers
# COPY requirements-optional.txt .
# RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
# RUN pip install --no-cache-dir -r requirements-optional.txt
```

## FAQ

**Q: Why split dependencies instead of using optional extras?**  
A: Docker layer caching works better with separate files. Can COPY only needed files.

**Q: What if I need both providers in production?**  
A: Use `requirements.txt` in Dockerfile (includes both).

**Q: Why torch-cpu index URL?**  
A: Default torch includes 3GB CUDA libraries. CPU-only version is 150MB.

**Q: Can I add more optional provider files?**  
A: Yes! Example: `requirements-cohere.txt` for Cohere reranking.

**Q: How do I know which file to use?**  
A: Check your `.env` config:
- `EMBEDDING_PROVIDER=vertex_ai` → requirements-base.txt
- `EMBEDDING_PROVIDER=sentence_transformers` → requirements-optional.txt

## Related Documentation

- [Development Guide](development.md) - Local setup and environment configuration
- [Deployment Guide](deployment.md) - Production deployment to Cloud Run
- [Architecture Decision](../README.md) - Why factory pattern for providers
