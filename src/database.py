"""
Database module for PostgreSQL + pgvector

This module provides vector storage and similarity search using PostgreSQL.
Multi-cloud portable - works on GCP Cloud SQL, AWS RDS, Azure Database for PostgreSQL.
"""

import hashlib
import hashlib
import json
import logging
import os
from typing import List, Optional, Tuple

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


class VectorDB:
    """PostgreSQL + pgvector vector database"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        # Get DATABASE_URL and clean it for asyncpg (remove +asyncpg suffix)
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://user:password@localhost:5432/raglab"
        )
        # asyncpg doesn't understand 'postgresql+asyncpg://', only 'postgresql://'
        self.connection_string = db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    async def connect(self):
        """Initialize connection pool"""
        async def init_connection(conn):
            """Register vector type for each new connection in the pool"""
            await register_vector(conn)
        
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=10,
            init=init_connection,  # Register vector type for EVERY connection
        )
        
        # Enable pgvector extension (one-time setup)
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        
        logger.info(f"Connected to PostgreSQL: {self.connection_string.split('@')[1]}")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from PostgreSQL")
    
    async def init_schema(self):
        """Create tables and indexes"""
        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Original documents table (metadata only, files in GCS)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS original_documents (
                    id SERIAL PRIMARY KEY,
                    doc_uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER,
                    file_hash TEXT UNIQUE NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    uploaded_by TEXT NOT NULL,
                    uploaded_at TIMESTAMP NOT NULL,
                    uploaded_via TEXT DEFAULT 'api',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Document chunks table (only embeddings, text in GCS)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id SERIAL PRIMARY KEY,
                    original_doc_id INTEGER REFERENCES original_documents(id) ON DELETE CASCADE,
                    embedding VECTOR(768) NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(original_doc_id, chunk_index)
                )
            """)
            
            # HNSW index for fast vector search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
                ON document_chunks 
                USING hnsw (embedding vector_cosine_ops)
            """)
            
            # GIN index for metadata filtering (MongoDB-style queries on JSONB)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_metadata 
                ON original_documents USING gin(metadata)
            """)
            
            # B-tree indexes for system column fields (most common filters)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by 
                ON original_documents (uploaded_by)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at 
                ON original_documents (uploaded_at)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_file_type 
                ON original_documents (file_type)
            """)
            
            logger.info("Database schema initialized (GCS + UUID + system columns + metadata filtering)")
    
    async def check_document_exists(self, file_hash: str) -> Optional[Tuple[int, str, str]]:
        """
        Check if document with given hash already exists
        
        Args:
            file_hash: SHA256 hash of file content
        
        Returns:
            Tuple of (doc_id, doc_uuid, filename) if exists, None otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, doc_uuid, filename FROM original_documents WHERE file_hash = $1",
                file_hash
            )
            if row:
                return row["id"], str(row["doc_uuid"]), row["filename"]
            return None
    
    async def insert_original_document(
        self,
        filename: str,
        file_type: str,
        file_size: int,
        file_hash: str,
        uploaded_by: str,
        uploaded_at,  # datetime object
        uploaded_via: str = "api",
        metadata: Optional[dict] = None,
    ) -> Tuple[int, str]:
        """
        Insert original document metadata (files stored in GCS)
        
        Args:
            filename: Original filename
            file_type: MIME type
            file_size: Size in bytes
            file_hash: SHA256 hash for deduplication
            uploaded_by: User email (from JWT)
            uploaded_at: Upload timestamp
            uploaded_via: Upload source (api, cli, etc.)
            metadata: User-defined metadata only (no system fields)
        
        Returns:
            Tuple of (document_id, doc_uuid)
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO original_documents 
                    (filename, file_type, file_size, file_hash, 
                     uploaded_by, uploaded_at, uploaded_via, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, doc_uuid
                """,
                filename,
                file_type,
                file_size,
                file_hash,
                uploaded_by,
                uploaded_at,
                uploaded_via,
                json.dumps(metadata) if metadata else json.dumps({}),
            )
            return row["id"], str(row["doc_uuid"])
    
    async def insert_chunk(
        self,
        original_doc_id: int,
        embedding: List[float],
        chunk_index: int,
    ) -> int:
        """
        Insert document chunk embedding (text stored in GCS)
        
        Returns:
            Chunk ID
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO document_chunks 
                    (original_doc_id, embedding, chunk_index)
                VALUES ($1, $2, $3)
                ON CONFLICT (original_doc_id, chunk_index) DO UPDATE
                    SET embedding = EXCLUDED.embedding
                RETURNING id
                """,
                original_doc_id,
                embedding,
                chunk_index,
            )
            return row["id"]
    
    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
        filters: Optional[dict] = None,
    ) -> List[dict]:
        """
        Search for similar chunks using cosine similarity with optional metadata filtering
        
        Args:
            query_embedding: Query vector
            top_k: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0.0-1.0). Results below this are filtered out.
            filters: MongoDB-style metadata filters (e.g., {"user_id": "user123", "tags": {"$in": ["finance"]}})
        
        Returns chunk indices with doc_uuid for fetching from GCS
        """
        # Build WHERE clause with optional filters
        where_conditions = ["(1 - (c.embedding <=> $1::vector)) >= $3"]
        params = [query_embedding, top_k, min_similarity]
        
        if filters:
            from .lib.filter_parser import FilterParseError, _parse_filters_with_offset
            
            try:
                # Offset by 3: $1=embedding, $2=top_k, $3=min_similarity
                filter_clause, filter_params = _parse_filters_with_offset(
                    filters, table_alias="d", param_offset=3
                )
                where_conditions.append(f"({filter_clause})")
                params.extend(filter_params)
            except FilterParseError as e:
                logger.error(f"Filter parsing failed: {e}")
                raise ValueError(f"Invalid filter syntax: {e}")
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
            SELECT 
                c.id as chunk_id,
                c.chunk_index,
                c.original_doc_id,
                d.doc_uuid,
                d.filename,
                d.file_type,
                d.metadata as doc_metadata,
                1 - (c.embedding <=> $1::vector) as similarity
            FROM document_chunks c
            JOIN original_documents d ON c.original_doc_id = d.id
            WHERE {where_clause}
            ORDER BY c.embedding <=> $1::vector
            LIMIT $2
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "chunk_index": row["chunk_index"],
                    "original_doc_id": row["original_doc_id"],
                    "doc_uuid": str(row["doc_uuid"]),
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "doc_metadata": json.loads(row["doc_metadata"]) if isinstance(row["doc_metadata"], str) else row["doc_metadata"],
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ]
    
    async def get_document_uuid(self, doc_id: int) -> Optional[str]:
        """Get document UUID by ID (for GCS path construction)"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT doc_uuid FROM original_documents WHERE id = $1",
                doc_id,
            )
            return str(row["doc_uuid"]) if row else None
    
    async def get_original_document(self, doc_id: int) -> Optional[dict]:
        """Retrieve document metadata by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    id,
                    doc_uuid,
                    filename,
                    file_type,
                    file_size,
                    chunk_count,
                    metadata,
                    uploaded_at
                FROM original_documents
                WHERE id = $1
                """,
                doc_id,
            )
            if not row:
                return None
            
            return {
                "id": row["id"],
                "doc_uuid": str(row["doc_uuid"]),
                "filename": row["filename"],
                "file_type": row["file_type"],
                "file_size": row["file_size"],
                "chunk_count": row["chunk_count"],
                "metadata": row["metadata"],
                "uploaded_at": row["uploaded_at"],
            }
    
    async def delete_document(self, doc_id: int):
        """Delete original document (cascades to all chunks)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM original_documents WHERE id = $1",
                doc_id,
            )
    
    async def delete_document_by_hash(self, file_hash: str) -> Optional[dict]:
        """
        Delete document by file hash (returns info about deleted document)
        
        Returns:
            dict with deleted document info, or None if not found
        """
        async with self.pool.acquire() as conn:
            # First, get document info
            row = await conn.fetchrow(
                """
                SELECT id, doc_uuid, filename, file_type, file_size, chunk_count
                FROM original_documents 
                WHERE file_hash = $1
                """,
                file_hash,
            )
            
            if not row:
                return None
            
            # Delete (cascades to chunks)
            await conn.execute(
                "DELETE FROM original_documents WHERE file_hash = $1",
                file_hash,
            )
            
            return {
                "id": row["id"],
                "doc_uuid": str(row["doc_uuid"]),
                "filename": row["filename"],
                "file_type": row["file_type"],
                "file_size": row["file_size"],
                "chunk_count": row["chunk_count"],
            }
    
    async def count_documents(self) -> int:
        """Get total original document count"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM original_documents")
    
    async def count_chunks(self) -> int:
        """Get total chunk count"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
    
    async def update_chunk_count(self, doc_id: int, count: int):
        """Update chunk count for document"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE original_documents SET chunk_count = $1 WHERE id = $2",
                count,
                doc_id,
            )
    
    async def get_document_by_uuid(self, doc_uuid: str) -> Optional[dict]:
        """Get document info by UUID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, doc_uuid, filename, file_type, chunk_count
                FROM original_documents
                WHERE doc_uuid = $1
                """,
                doc_uuid,
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "doc_uuid": str(row["doc_uuid"]),
                "filename": row["filename"],
                "file_type": row["file_type"],
                "chunk_count": row["chunk_count"],
            }


# Global database instance
vector_db = VectorDB()
