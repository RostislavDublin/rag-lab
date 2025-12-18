"""
Integration tests for Phase 2: Hybrid Search Storage (PostgreSQL + GCS)

Tests database schema changes and BM25 index storage:
- New columns: summary TEXT, keywords TEXT[], token_count INTEGER
- New GIN index on keywords array
- BM25 index upload/download from GCS
- Database insert/retrieve with hybrid fields
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import List

import pytest
import pytest_asyncio

from src.database import VectorDB
from src.storage import DocumentStorage
from src.bm25 import build_bm25_index


@pytest.mark.asyncio
class TestHybridStorageIntegration:
    """Integration tests for hybrid search storage layer"""
    
    @pytest_asyncio.fixture
    async def vector_db(self):
        """Initialize database connection"""
        db = VectorDB()
        await db.connect()
        await db.init_schema()  # Create tables with hybrid fields
        yield db
        await db.pool.close()
    
    @pytest.fixture
    def document_storage(self):
        """Initialize GCS storage"""
        bucket_name = os.getenv("GCS_BUCKET", "raglab-documents-test")
        return DocumentStorage(bucket_name=bucket_name)
    
    async def test_database_schema_with_hybrid_fields(self, vector_db):
        """Test that database schema includes hybrid search fields"""
        async with vector_db.pool.acquire() as conn:
            # Check table structure
            result = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'original_documents'
                ORDER BY ordinal_position
            """)
            
            columns = {row['column_name']: row['data_type'] for row in result}
            
            # Verify hybrid fields exist
            assert 'summary' in columns, "summary column missing"
            assert columns['summary'] == 'text', "summary should be TEXT"
            
            assert 'keywords' in columns, "keywords column missing"
            assert columns['keywords'] == 'ARRAY', "keywords should be TEXT[]"
            
            assert 'token_count' in columns, "token_count column missing"
            assert columns['token_count'] == 'integer', "token_count should be INTEGER"
    
    async def test_keywords_gin_index_exists(self, vector_db):
        """Test that GIN index on keywords array was created"""
        async with vector_db.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE tablename = 'original_documents' 
                AND indexname = 'idx_documents_keywords'
            """)
            
            assert result == 1, "GIN index on keywords not found"
            
            # Check index type
            index_def = await conn.fetchval("""
                SELECT indexdef 
                FROM pg_indexes 
                WHERE indexname = 'idx_documents_keywords'
            """)
            
            assert 'gin' in index_def.lower(), "Index should be GIN type"
            assert 'keywords' in index_def.lower(), "Index should be on keywords column"
    
    async def test_insert_document_with_hybrid_fields(self, vector_db):
        """Test inserting document with summary, keywords, token_count"""
        # Sample hybrid data
        summary = "Kubernetes deployment guide covering pod configuration and scaling."
        keywords = ["kubernetes", "deployment", "pod", "scaling", "configuration"]
        token_count = 1250
        
        # Insert document
        doc_id, doc_uuid = await vector_db.insert_original_document(
            filename="k8s-guide.pdf",
            file_type="application/pdf",
            file_size=50000,
            file_hash="test_hash_" + datetime.now().isoformat(),
            uploaded_by="test@example.com",
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            uploaded_via="api",
            metadata={"category": "devops"},
            summary=summary,
            keywords=keywords,
            token_count=token_count
        )
        
        assert doc_id > 0, "Document ID should be positive"
        assert doc_uuid, "Document UUID should be generated"
        
        # Retrieve and verify
        async with vector_db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary, keywords, token_count FROM original_documents WHERE id = $1",
                doc_id
            )
            
            assert row['summary'] == summary, "Summary not saved correctly"
            assert row['keywords'] == keywords, "Keywords not saved correctly"
            assert row['token_count'] == token_count, "Token count not saved correctly"
        
        # Cleanup
        await vector_db.delete_document(doc_id)
    
    async def test_keywords_array_filtering(self, vector_db):
        """Test filtering documents by keywords array"""
        # Insert test documents
        doc1_id, _ = await vector_db.insert_original_document(
            filename="k8s-doc.pdf",
            file_type="application/pdf",
            file_size=1000,
            file_hash="hash1_" + datetime.now().isoformat(),
            uploaded_by="test@example.com",
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            keywords=["kubernetes", "docker", "deployment"]
        )
        
        doc2_id, _ = await vector_db.insert_original_document(
            filename="aws-doc.pdf",
            file_type="application/pdf",
            file_size=2000,
            file_hash="hash2_" + datetime.now().isoformat(),
            uploaded_by="test@example.com",
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            keywords=["aws", "ec2", "s3"]
        )
        
        # Query with array containment operator
        async with vector_db.pool.acquire() as conn:
            # Find docs with 'kubernetes' in keywords
            result = await conn.fetch("""
                SELECT id, filename 
                FROM original_documents 
                WHERE 'kubernetes' = ANY(keywords)
            """)
            
            ids = [row['id'] for row in result]
            assert doc1_id in ids, "Should find k8s document"
            assert doc2_id not in ids, "Should not find AWS document"
        
        # Cleanup
        await vector_db.delete_document(doc1_id)
        await vector_db.delete_document(doc2_id)
    
    async def test_gcs_bm25_index_upload_download(self, document_storage):
        """Test uploading and downloading BM25 index to/from GCS"""
        # Skip if no GCS credentials
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("GCP_PROJECT_ID"):
            pytest.skip("GCS credentials not available")
        
        # Create test BM25 index
        chunks = [
            "Kubernetes pod deployment strategies",
            "Pod configuration with YAML files"
        ]
        bm25_index = build_bm25_index(chunks)
        
        # Test data
        test_uuid = "test-uuid-" + datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Upload document with BM25 index
        await document_storage.upload_document(
            doc_uuid=test_uuid,
            pdf_bytes=b"test pdf content",
            extracted_text="test text",
            chunks=[
                {"text": chunks[0], "index": 0},
                {"text": chunks[1], "index": 1}
            ],
            file_type="pdf",
            bm25_index=bm25_index
        )
        
        # Download and verify BM25 index
        blob = document_storage.bucket.blob(f"{test_uuid}/bm25_doc_index.json")
        exists = await asyncio.to_thread(blob.exists)
        assert exists, "BM25 index file should exist in GCS"
        
        # Read content
        content = await asyncio.to_thread(blob.download_as_bytes)
        downloaded_index = json.loads(content)
        
        # Verify structure
        assert "term_frequencies" in downloaded_index, "Should have term_frequencies key"
        assert isinstance(downloaded_index["term_frequencies"], dict), "term_frequencies should be dict"
        
        # Verify some expected terms (Snowball stemming)
        tf = downloaded_index["term_frequencies"]
        assert "pod" in tf, "Should contain 'pod' term"
        assert tf["pod"] == 2, "'pod' should appear twice"
        assert "kubernet" in tf, "Should contain 'kubernet' stem (from 'kubernetes')"
        
        # Cleanup
        await document_storage.delete_document(test_uuid)
    
    async def test_null_hybrid_fields_allowed(self, vector_db):
        """Test that hybrid fields can be NULL (optional for backwards compatibility)"""
        # Insert without hybrid fields
        doc_id, doc_uuid = await vector_db.insert_original_document(
            filename="legacy-doc.pdf",
            file_type="application/pdf",
            file_size=1000,
            file_hash="legacy_hash_" + datetime.now().isoformat(),
            uploaded_by="test@example.com",
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            # No summary, keywords, token_count
        )
        
        # Verify NULL values
        async with vector_db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary, keywords, token_count FROM original_documents WHERE id = $1",
                doc_id
            )
            
            assert row['summary'] is None, "summary should be NULL when not provided"
            assert row['keywords'] == [], "keywords should be empty array when not provided"
            assert row['token_count'] is None, "token_count should be NULL when not provided"
        
        # Cleanup
        await vector_db.delete_document(doc_id)


class TestBM25IndexBuilder:
    """Unit tests for BM25 index builder (integration with tokenizer)"""
    
    def test_build_bm25_index_structure(self):
        """Test BM25 index has correct structure"""
        chunks = ["test chunk one", "test chunk two"]
        index = build_bm25_index(chunks)
        
        assert "term_frequencies" in index, "Should have term_frequencies key"
        assert isinstance(index["term_frequencies"], dict), "term_frequencies should be dict"
        assert len(index) == 1, "Should only have term_frequencies (minimal structure)"
    
    def test_build_bm25_index_aggregation(self):
        """Test term frequency aggregation across chunks"""
        chunks = [
            "kubernetes pod deployment",
            "pod configuration yaml",
            "kubernetes deployment strategies"
        ]
        index = build_bm25_index(chunks)
        tf = index["term_frequencies"]
        
        # Verify aggregation (Snowball stemming)
        assert tf["kubernet"] == 2, "kubernet (from 'kubernetes') appears in chunks 0 and 2"
        assert tf["pod"] == 2, "pod appears in chunks 0 and 1"
        assert tf["deploy"] == 2, "deploy (from 'deployment') appears in chunks 0 and 2"
        assert tf["configur"] == 1, "configur (from 'configuration') appears once"
        assert tf["yaml"] == 1, "yaml appears once"
        assert tf["strategi"] == 1, "strategi (from 'strategies') appears once"
