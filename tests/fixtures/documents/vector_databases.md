# Vector Databases for RAG Systems

## Introduction

Vector databases are specialized storage systems designed for efficient similarity search over high-dimensional embeddings. They are essential for building production-ready RAG applications.

## Popular Vector Databases

### pgvector (PostgreSQL extension)
- **Pros**: Runs in existing PostgreSQL, ACID transactions, SQL queries
- **Cons**: Slower than specialized databases at massive scale
- **Best for**: Small to medium datasets, when you already use PostgreSQL

### Pinecone
- **Pros**: Fully managed, very fast, good SDKs
- **Cons**: Vendor lock-in, can be expensive
- **Best for**: Production apps needing high performance without ops overhead

### Weaviate
- **Pros**: Open source, hybrid search (vector + keyword), GraphQL API
- **Cons**: More complex to self-host
- **Best for**: Complex search requirements, need for both semantic and keyword search

## Architecture Decisions

When choosing a vector database, consider:

1. **Scale**: How many vectors will you store? (pgvector: <1M, Pinecone: >10M)
2. **Latency**: What query speed do you need? (<100ms for user-facing apps)
3. **Cost**: Managed services vs self-hosted infrastructure
4. **Lock-in**: Can you migrate later if needed?

## Implementation Example

```python
# Using pgvector with PostgreSQL
import asyncpg
from pgvector.asyncpg import register_vector

# Connect to database
conn = await asyncpg.connect("postgresql://localhost/ragdb")
await register_vector(conn)

# Store embeddings
await conn.execute("""
    INSERT INTO embeddings (text, embedding)
    VALUES ($1, $2)
""", chunk_text, embedding_vector)

# Similarity search
results = await conn.fetch("""
    SELECT text, 1 - (embedding <=> $1) AS similarity
    FROM embeddings
    ORDER BY embedding <=> $1
    LIMIT 5
""", query_embedding)
```

## Conclusion

For most RAG projects starting out, pgvector offers the best balance of simplicity and capability. You can always migrate to a specialized vector database later as you scale.

---

*Last updated: December 2025*
*Tags: #rag #vector-search #databases #embeddings*
