# Docker Compose Local Development

Quick start for local development with PostgreSQL + pgvector.

## Prerequisites

- Docker & Docker Compose installed
- (Optional) GCP Service Account key for Vertex AI

## Usage

### 1. Start Services

```bash
# Start PostgreSQL + API
docker-compose up -d

# View logs
docker-compose logs -f api
```

### 2. Test API

```bash
# Health check
curl http://localhost:8080/health

# Upload document
curl -X POST http://localhost:8080/v1/documents/upload \
  -F "file=@sample.pdf"

# Query
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?", "top_k": 3}'
```

### 3. Stop Services

```bash
docker-compose down

# Remove volumes (delete data)
docker-compose down -v
```

## Configuration

Set environment variables in `.env` file:

```bash
# .env
GCP_PROJECT_ID=your-gcp-project
GCP_LOCATION=us-central1
GCS_BUCKET=your-bucket-name

# Optional: Enable reranking for better search quality
RERANKER_ENABLED=true
RERANKER_TYPE=gemini  # or "local" for offline cross-encoder
RERANKER_MODEL=gemini-2.0-flash-exp
```

Or export before running:

```bash
export GCP_PROJECT_ID=your-project-id
export RERANKER_ENABLED=true
docker-compose up -d
```

## Database Access

Connect to PostgreSQL:

```bash
docker exec -it raglab-postgres psql -U raglab -d raglab
```

Query data:

```sql
-- Check documents
SELECT id, filename, uploaded_at FROM original_documents;

-- Check chunks
SELECT COUNT(*) FROM document_chunks;

-- Vector search test
SELECT chunk_text, 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) as similarity
FROM document_chunks
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

## Development Mode

API has hot reload enabled - edit `src/` files and changes auto-apply.

```bash
# Rebuild after dependency changes
docker-compose up -d --build
```
