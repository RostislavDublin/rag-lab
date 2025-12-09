"""
Database module for PostgreSQL + pgvector

This module provides vector storage and similarity search using PostgreSQL.
Multi-cloud portable - works on GCP Cloud SQL, AWS RDS, Azure Database for PostgreSQL.
"""

import os
from typing import List, Optional, Tuple

import asyncpg
from pgvector.asyncpg import register_vector


class VectorDB:
    """PostgreSQL + pgvector vector database"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.connection_string = os.getenv(
            "DATABASE_URL",
            "postgresql://user:password@localhost:5432/raglab"
        )
    
    async def connect(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=10,
        )
        
        # Register pgvector type
        async with self.pool.acquire() as conn:
            await register_vector(conn)
        
        print(f"Connected to PostgreSQL: {self.connection_string.split('@')[1]}")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("Disconnected from PostgreSQL")
    
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
                    chunk_count INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{}',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Document chunks table (only embeddings, text in GCS)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id SERIAL PRIMARY KEY,
                    original_doc_id INTEGER REFERENCES original_documents(id) ON DELETE CASCADE,
                    embedding VECTOR(1408) NOT NULL,
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
            
            print("Database schema initialized (GCS + UUID architecture)")
    
    async def insert_original_document(
        self,
        filename: str,
        file_type: str,
        file_size: int,
        metadata: Optional[dict] = None,
    ) -> Tuple[int, str]:
        """
        Insert original document metadata (files stored in GCS)
        
        Returns:
            Tuple of (document_id, doc_uuid)
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO original_documents 
                    (filename, file_type, file_size, metadata)
                VALUES ($1, $2, $3, $4)
                RETURNING id, doc_uuid
                """,
                filename,
                file_type,
                file_size,
                metadata or {},
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
    ) -> List[dict]:
        """
        Search for similar chunks using cosine similarity
        
        Returns chunk indices with doc_uuid for fetching from GCS
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
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
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                query_embedding,
                top_k,
            )
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "chunk_index": row["chunk_index"],
                    "original_doc_id": row["original_doc_id"],
                    "doc_uuid": str(row["doc_uuid"]),
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "doc_metadata": row["doc_metadata"],
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


# Global database instance
vector_db = VectorDB()
