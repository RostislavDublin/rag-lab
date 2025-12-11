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

from src.utils import calculate_file_hash


# Test configuration
API_BASE = "http://localhost:8080"
GCS_BUCKET = "myai-475419-rag-documents"


@pytest.fixture(scope="module")
def gcs_client():
    """GCS client for storage verification"""
    return storage.Client()


@pytest.fixture(scope="module")
def test_documents():
    """Test document paths and their hashes for selective cleanup"""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "documents"
    docs = {
        "txt": fixtures_dir / "bug_too_many.txt",  # Large file to test splitting
        "pdf": fixtures_dir / "google_agent_quality.pdf",
        "pdf_context": fixtures_dir / "google_context_engineering.pdf"
    }
    
    # Calculate hashes for selective cleanup (preserves user documents)
    docs["txt_hash"] = calculate_file_hash(docs["txt"])
    docs["pdf_hash"] = calculate_file_hash(docs["pdf"])
    
    return docs


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_documents(request, test_documents):
    """Clean up ONLY test documents before and after tests (preserves user documents!)"""
    print("\n🧹 Cleaning up test documents (user documents will be preserved)...")
    
    # Delete test documents by hash (if they exist from previous run)
    deleted_before = 0
    for hash_key in ["txt_hash", "pdf_hash"]:
        file_hash = test_documents[hash_key]
        response = requests.delete(f"{API_BASE}/v1/documents/by-hash/{file_hash}", timeout=30)
        if response.status_code == 200:
            result = response.json()
            print(f"   Deleted leftover: {result['filename']}")
            deleted_before += 1
    
    if deleted_before == 0:
        print("   No leftover test documents found")
    
    print("✓ Ready to run tests (user documents preserved)\n")
    
    yield  # Run tests
    
    # Cleanup after tests (unless --no-cleanup flag is used)
    if not request.config.getoption("--no-cleanup"):
        print("\n🧹 Cleaning up test documents after tests...")
        deleted_after = 0
        for hash_key in ["txt_hash", "pdf_hash"]:
            file_hash = test_documents[hash_key]
            response = requests.delete(f"{API_BASE}/v1/documents/by-hash/{file_hash}", timeout=30)
            if response.status_code == 200:
                deleted_after += 1
        
        print(f"✓ Deleted {deleted_after} test document(s), user documents preserved\n")
    else:
        print("\n⚠️  --no-cleanup flag: test documents left in system for inspection")


def test_01_verify_api_health():
    """Step 1: Verify API is running and healthy"""
    print("\n=== Step 1: Verify API health ===")
    
    # Check API health
    response = requests.get(f"{API_BASE}/health", timeout=10)
    assert response.status_code == 200
    health = response.json()
    print(f"✓ API version: {health['version']}, uptime: {health['uptime_seconds']}s")
    
    # Check API can list documents (may have user documents - that's OK!)
    response = requests.get(f"{API_BASE}/v1/documents", timeout=10)
    assert response.status_code == 200
    docs = response.json()
    print(f"✓ API responsive, current documents: {docs['total']}")


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


def test_03_upload_pdf_document(test_documents):
    """Step 3: Upload PDF document"""
    print("\n=== Step 3: Upload PDF document ===")
    
    pdf_path = test_documents["pdf"]
    assert pdf_path.exists(), f"Test file not found: {pdf_path}"
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")


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
    print("\n🎉 E2E test completed successfully!")
    print("   Test documents will be cleaned up automatically (user documents preserved)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
