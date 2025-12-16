# API Reference

Complete REST API documentation for RAG Lab.

## Base URL

- **Local Development:** `http://localhost:8080`
- **Cloud Run:** `https://rag-api-HASH-uc.a.run.app`

## Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "storage": "accessible"
}
```

## Upload Documents

Upload one or more documents for processing.

```bash
POST /upload
Content-Type: multipart/form-data

files: file1.pdf, file2.txt (multiple files allowed)
metadata: {"category": "technical", "author": "AI Team"}  # Optional JSON
```

**Example:**
```bash
curl -X POST http://localhost:8080/upload \
  -F "files=@document1.pdf" \
  -F "files=@document2.txt" \
  -F 'metadata={"category":"technical","priority":"high"}'
```

**Response:**
```json
{
  "uploaded_files": [
    {
      "filename": "document1.pdf",
      "document_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "total_chunks": 42,
      "metadata": {
        "category": "technical",
        "priority": "high"
      }
    }
  ]
}
```

## Hybrid Search

Perform hybrid search combining semantic similarity and metadata filtering.

```bash
POST /search
Content-Type: application/json

{
  "query": "How does authentication work?",
  "top_k": 5,
  "metadata_filter": {
    "category": {"$eq": "technical"}
  },
  "rerank": true,
  "rerank_top_k": 3
}
```

**Parameters:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search query text |
| `top_k` | integer | No | 10 | Number of results to return (before reranking) |
| `metadata_filter` | object | No | null | MongoDB-style filter for metadata |
| `rerank` | boolean | No | false | Enable LLM reranking with Gemini |
| `rerank_top_k` | integer | No | 5 | Number of results after reranking |

**Response:**
```json
{
  "results": [
    {
      "document_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "auth-guide.pdf",
      "chunk_index": 3,
      "text": "Authentication uses JWT tokens with JWKS validation...",
      "similarity_score": 0.8765,
      "rerank_score": 0.95,
      "rerank_reasoning": "Directly answers authentication mechanism question with implementation details.",
      "metadata": {
        "category": "technical",
        "author": "Security Team"
      }
    }
  ],
  "total_results": 1,
  "reranked": true
}
```

**Notes:**
- `similarity_score`: Cosine similarity (0-1, higher is better)
- `rerank_score`: LLM relevance score (0-1, higher is better, only when `rerank=true`)
- `rerank_reasoning`: Explanation of why result is relevant (only when `rerank=true`)
- Results sorted by `rerank_score` if reranking enabled, otherwise by `similarity_score`

## Metadata Filtering

RAG Lab uses **MongoDB query operators** for flexible metadata filtering.

### Basic Operators

#### Equality (`$eq`)

Find exact matches:

```json
{
  "metadata_filter": {
    "category": {"$eq": "technical"}
  }
}
```

**Shorthand:**
```json
{
  "metadata_filter": {
    "category": "technical"  // Same as {"$eq": "technical"}
  }
}
```

#### Inequality (`$ne`)

Exclude specific values:

```json
{
  "metadata_filter": {
    "status": {"$ne": "archived"}
  }
}
```

#### Greater Than / Less Than

Numeric comparisons:

```json
{
  "metadata_filter": {
    "priority": {"$gte": 5},      // >= 5
    "size_mb": {"$lt": 10}         // < 10
  }
}
```

**Operators:** `$gt` (>), `$gte` (>=), `$lt` (<), `$lte` (<=)

#### In / Not In (`$in`, `$nin`)

Match any/none from list:

```json
{
  "metadata_filter": {
    "department": {"$in": ["Engineering", "Product"]},
    "status": {"$nin": ["deleted", "archived"]}
  }
}
```

### Logical Operators

#### AND (implicit)

Multiple conditions at same level are ANDed:

```json
{
  "metadata_filter": {
    "category": "technical",
    "priority": {"$gte": 5}
  }
}
// Matches: category="technical" AND priority >= 5
```

#### OR (`$or`)

Match any condition:

```json
{
  "metadata_filter": {
    "$or": [
      {"priority": {"$gte": 8}},
      {"urgent": true}
    ]
  }
}
// Matches: priority >= 8 OR urgent = true
```

#### NOT (`$not`)

Negate a condition:

```json
{
  "metadata_filter": {
    "category": {"$not": {"$eq": "draft"}}
  }
}
// Matches: category != "draft"
```

#### NOR (`$nor`)

Match none of the conditions:

```json
{
  "metadata_filter": {
    "$nor": [
      {"status": "deleted"},
      {"archived": true}
    ]
  }
}
// Matches: NOT (status="deleted" OR archived=true)
```

### Complex Queries

Combine operators for advanced filtering:

```json
{
  "query": "authentication methods",
  "metadata_filter": {
    "$and": [
      {
        "$or": [
          {"category": "security"},
          {"tags": {"$in": ["auth", "oauth"]}}
        ]
      },
      {"priority": {"$gte": 5}},
      {"status": {"$ne": "archived"}}
    ]
  },
  "rerank": true
}
```

**Translation:** Find documents where:
- (category is "security" OR tags contain "auth"/"oauth") AND
- priority >= 5 AND
- status is not "archived"

### Best Practices

1. **Use implicit AND for simple filters:**
   ```json
   {"category": "tech", "priority": 5}  // Cleaner than explicit $and
   ```

2. **Combine $or with other filters:**
   ```json
   {
     "status": "active",  // AND this
     "$or": [             // with (this OR that)
       {"urgent": true},
       {"priority": {"$gte": 8}}
     ]
   }
   ```

3. **Index frequently filtered fields:**
   ```sql
   CREATE INDEX idx_category ON document_chunks(metadata->'category');
   CREATE INDEX idx_priority ON document_chunks(((metadata->>'priority')::int));
   ```

## List Documents

Get metadata for all uploaded documents.

```bash
GET /documents
```

**Response:**
```json
{
  "documents": [
    {
      "document_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "auth-guide.pdf",
      "total_chunks": 42,
      "upload_timestamp": "2025-01-15T10:30:00Z",
      "metadata": {
        "category": "technical",
        "author": "Security Team"
      }
    }
  ],
  "total_count": 1
}
```

## Get Document

Retrieve specific document metadata.

```bash
GET /documents/{document_uuid}
```

**Response:**
```json
{
  "document_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "auth-guide.pdf",
  "total_chunks": 42,
  "upload_timestamp": "2025-01-15T10:30:00Z",
  "metadata": {
    "category": "technical",
    "author": "Security Team"
  },
  "chunks": [
    {
      "chunk_index": 0,
      "text": "Introduction to Authentication...",
      "embedding_preview": [0.123, -0.456, ...]
    }
  ]
}
```

## Download Document

Download original or extracted text.

```bash
GET /documents/{document_uuid}/download?type=original
GET /documents/{document_uuid}/download?type=extracted
```

**Parameters:**
- `type`: `original` (PDF/DOCX) or `extracted` (plain text)

**Response:** File download with appropriate Content-Type

## Delete Document

Remove document and all its chunks from database and storage.

```bash
DELETE /documents/{document_uuid}
```

**Response:**
```json
{
  "message": "Document 550e8400-e29b-41d4-a716-446655440000 deleted",
  "chunks_deleted": 42
}
```

## Update Metadata

Update metadata for existing document.

```bash
PATCH /documents/{document_uuid}/metadata
Content-Type: application/json

{
  "category": "security",
  "reviewed": true,
  "reviewer": "alice@example.com"
}
```

**Response:**
```json
{
  "document_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "category": "security",
    "reviewed": true,
    "reviewer": "alice@example.com"
  }
}
```

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes:**

| Code | Meaning | Example |
|------|---------|---------|
| 400 | Bad Request | Invalid metadata filter syntax |
| 404 | Not Found | Document UUID doesn't exist |
| 422 | Validation Error | Missing required field in request |
| 500 | Server Error | Database connection failed |

## Rate Limiting

- **Local:** No rate limits
- **Cloud Run:** Subject to GCP quotas
- **Recommended:** Implement client-side throttling for bulk operations

## OpenAPI Schema

Interactive API documentation available at:

```
http://localhost:8080/docs       # Swagger UI
http://localhost:8080/redoc      # ReDoc
```
