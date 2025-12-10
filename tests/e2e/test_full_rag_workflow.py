"""
End-to-End test for complete RAG workflow

Tests the full lifecycle:
1. Verify system is empty
2. Upload documents (PDF + TXT)
3. Query and get relevant chunks
4. Download original files
5. Delete documents
6. Verify cleanup (DB + GCS)
"""

import os
import tempfile
from pathlib import Path

import pytest
import requests
from google.cloud import storage


# Test configuration
API_BASE = "http://localhost:8080"
GCS_BUCKET = "myai-475419-rag-documents"


@pytest.fixture(scope="module")
def gcs_client():
    """GCS client for storage verification"""
    return storage.Client()


@pytest.fixture(scope="module", autouse=True)
def cleanup_before_tests(gcs_client):
    """Clean up system before running tests"""
    print("\n🧹 Cleaning up system before tests...")
    
    # Delete all documents via API
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    if response.status_code == 200:
        docs = response.json()["documents"]
        for doc in docs:
            requests.delete(f"{API_BASE}/v1/documents/{doc['doc_id']}", timeout=30)
        if docs:
            print(f"   Deleted {len(docs)} existing document(s)")
    
    # Verify GCS is clean
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs())
    if blobs:
        print(f"   Warning: {len(blobs)} orphaned objects in GCS (should not happen)")
    
    print("✓ System is clean, starting tests\n")


@pytest.fixture(scope="module")
def test_documents():
    """Test document paths"""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "documents"
    return {
        "txt": fixtures_dir / "rag_architecture_guide.txt",
        "pdf": Path.home() / "Downloads" / "Квитанция за ноябрь 2025 (ЛС 990270090) МУП г.Сочи «Водоканал».pdf"
    }


def test_01_verify_system_empty(gcs_client):
    """Step 1: Verify PostgreSQL and GCS are empty"""
    print("\n=== Step 1: Verify system is empty ===")
    
    # Check API health
    response = requests.get(f"{API_BASE}/health", timeout=10)
    assert response.status_code == 200
    health = response.json()
    print(f"API version: {health['version']}, uptime: {health['uptime_seconds']}s")
    
    # Check PostgreSQL (via API)
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    assert response.status_code == 200
    docs = response.json()
    assert docs["total"] == 0, f"Expected 0 documents, found {docs['total']}"
    print(f"✓ PostgreSQL: 0 documents")
    
    # Check GCS
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs())
    assert len(blobs) == 0, f"Expected 0 GCS objects, found {len(blobs)}"
    print(f"✓ GCS: 0 objects")


def test_02_upload_txt_document(test_documents):
    """Step 2: Upload TXT document"""
    print("\n=== Step 2: Upload TXT document ===")
    
    txt_path = test_documents["txt"]
    assert txt_path.exists(), f"Test file not found: {txt_path}"
    
    with open(txt_path, "rb") as f:
        files = {"file": (txt_path.name, f, "text/plain")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    
    return result


def test_03_upload_pdf_document(test_documents):
    """Step 3: Upload PDF document"""
    print("\n=== Step 3: Upload PDF document ===")
    
    pdf_path = test_documents["pdf"]
    if not pdf_path.exists():
        pytest.skip(f"PDF test file not found: {pdf_path}")
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    
    return result


def test_04_list_documents():
    """Step 4: Verify documents are listed"""
    print("\n=== Step 4: List all documents ===")
    
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    assert response.status_code == 200
    
    docs = response.json()
    assert docs["total"] >= 1, "Expected at least 1 document"
    
    print(f"✓ Found {docs['total']} document(s):")
    for doc in docs["documents"]:
        print(f"  - [{doc['doc_id']}] {doc['filename']} ({doc['chunk_count']} chunks)")


def test_05_query_rag_system():
    """Step 5: Query RAG system and verify results"""
    print("\n=== Step 5: Query RAG system ===")
    
    query = "What is RAG?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 3},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned"
    assert len(result["results"]) > 0, "Empty results list"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} relevant chunks:")
    
    for i, chunk in enumerate(result["results"][:3], 1):
        print(f"\n  [{i}] Similarity: {chunk['similarity']:.3f}")
        print(f"      From: {chunk['filename']} (chunk {chunk['chunk_index']})")
        print(f"      Text: {chunk['chunk_text'][:100]}...")
    
    return result["results"][0]["original_doc_id"] if result["results"] else None


def test_06_download_document():
    """Step 6: Download original document"""
    print("\n=== Step 6: Download original document ===")
    
    # Get first document
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    docs = response.json()["documents"]
    
    if not docs:
        pytest.skip("No documents to download")
    
    doc_id = docs[0]["doc_id"]
    filename = docs[0]["filename"]
    
    response = requests.get(f"{API_BASE}/v1/documents/{doc_id}/download", timeout=30)
    assert response.status_code == 200, f"Download failed: {response.text}"
    
    content = response.content
    assert len(content) > 0, "Downloaded file is empty"
    
    print(f"✓ Downloaded: {filename}")
    print(f"  Size: {len(content):,} bytes")
    print(f"  Content-Type: {response.headers.get('content-type')}")


def test_07_verify_gcs_storage(gcs_client):
    """Step 7: Verify GCS contains all uploaded files"""
    print("\n=== Step 7: Verify GCS storage ===")
    
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs())
    
    assert len(blobs) > 0, "GCS bucket is empty"
    
    # Group by UUID
    uuids = set()
    file_types = {}
    
    for blob in blobs:
        uuid = blob.name.split('/')[0]
        uuids.add(uuid)
        file_type = blob.name.split('/')[-1]
        file_types[file_type] = file_types.get(file_type, 0) + 1
    
    print(f"✓ GCS contains {len(blobs)} objects for {len(uuids)} document(s)")
    print(f"  File types: {dict(file_types)}")


def test_08_delete_all_documents():
    """Step 8: Delete all documents"""
    print("\n=== Step 8: Delete all documents ===")
    
    # Get all documents
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    docs = response.json()["documents"]
    
    if not docs:
        print("  No documents to delete")
        return
    
    # Delete each document
    deleted_count = 0
    for doc in docs:
        response = requests.delete(f"{API_BASE}/v1/documents/{doc['doc_id']}", timeout=30)
        assert response.status_code == 200, f"Delete failed for doc {doc['doc_id']}"
        result = response.json()
        print(f"  ✓ Deleted: {result['filename']} ({result['chunks_deleted']} chunks)")
        deleted_count += 1
    
    print(f"\n✓ Deleted {deleted_count} document(s)")


def test_09_verify_cleanup(gcs_client):
    """Step 9: Verify complete cleanup (DB + GCS)"""
    print("\n=== Step 9: Verify complete cleanup ===")
    
    # Check PostgreSQL
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    assert response.status_code == 200
    docs = response.json()
    assert docs["total"] == 0, f"PostgreSQL not clean: {docs['total']} documents remain"
    print(f"✓ PostgreSQL: 0 documents")
    
    # Check GCS
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs())
    assert len(blobs) == 0, f"GCS not clean: {len(blobs)} objects remain"
    print(f"✓ GCS: 0 objects")
    
    print("\n🎉 E2E test completed successfully! System is clean.")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
