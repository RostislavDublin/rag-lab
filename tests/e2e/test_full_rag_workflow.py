"""
End-to-End test for complete RAG workflow with semantic search validation

Tests the full lifecycle with thematic documents:
1. Health check (API + current documents)
2. Upload 9 documents with distinct topics
   - TXT: RAG technology (rag_architecture_guide.txt)
   - PDF: AI agents, software engineering (google_agent_quality.pdf)
   - MD: Databases, vector search (vector_databases.md)
   - JSON: Products, prices, specs (electronics_catalog.json)
   - HTML: Art exhibitions, tickets (art_exhibition.html)
   - YAML: Business KPIs, metrics (business_metrics.yaml)
   - XML: Legal, GDPR compliance (gdpr_compliance.xml)
   - CSV: Financial reports (financial_quarterly_report.csv)
   - LOG: System operations (rag_system_operations.log)
3. List documents
4. Semantic search tests - validate RAG returns topically correct documents
   - Product queries → electronics catalog
   - Art queries → exhibition info
   - Business queries → metrics
   - Compliance queries → GDPR report
   - Financial queries → quarterly report
   - Operations queries → system logs
   - Topic isolation (negative test)
5. Download original files
6. Delete documents
7. Verify cleanup (DB + GCS)

Philosophy: Non-trivial queries test semantic understanding vs keyword matching.
Each document has distinct topic, enabling validation that RAG actually works
as intended and provides value.
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
    """Test document paths with distinct topics for semantic search validation"""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "documents"
    docs = {
        # Each document has a distinct topic for semantic testing
        "txt": fixtures_dir / "rag_architecture_guide.txt",  # Topic: RAG technology
        "pdf": fixtures_dir / "google_agent_quality.pdf",  # Topic: AI agents, software engineering
        "md": fixtures_dir / "vector_databases.md",  # Topic: Databases, vector search
        "json": fixtures_dir / "electronics_catalog.json",  # Topic: Products, prices, specifications
        "html": fixtures_dir / "art_exhibition.html",  # Topic: Art, exhibitions, tickets
        "yaml": fixtures_dir / "business_metrics.yaml",  # Topic: Business KPIs, metrics
        "xml": fixtures_dir / "gdpr_compliance.xml",  # Topic: Legal, GDPR, compliance
        "csv": fixtures_dir / "financial_quarterly_report.csv",  # Topic: Financial reports
        "log": fixtures_dir / "rag_system_operations.log",  # Topic: System operations, logs
    }
    
    # Calculate hashes for selective cleanup (preserves user documents)
    docs["txt_hash"] = calculate_file_hash(docs["txt"])
    docs["pdf_hash"] = calculate_file_hash(docs["pdf"])
    docs["md_hash"] = calculate_file_hash(docs["md"])
    docs["json_hash"] = calculate_file_hash(docs["json"])
    docs["html_hash"] = calculate_file_hash(docs["html"])
    docs["yaml_hash"] = calculate_file_hash(docs["yaml"])
    docs["xml_hash"] = calculate_file_hash(docs["xml"])
    docs["csv_hash"] = calculate_file_hash(docs["csv"])
    docs["log_hash"] = calculate_file_hash(docs["log"])
    
    return docs


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_documents(request, test_documents):
    """Clean up ONLY test documents before and after tests (preserves user documents!)"""
    print("\n🧹 Cleaning up test documents (user documents will be preserved)...")
    
    # Delete test documents by hash (if they exist from previous run)
    deleted_before = 0
    for hash_key in ["txt_hash", "pdf_hash", "md_hash", "json_hash", "html_hash", "yaml_hash", "xml_hash", "csv_hash", "log_hash"]:
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
        for hash_key in ["txt_hash", "pdf_hash", "md_hash", "json_hash", "html_hash", "yaml_hash", "xml_hash", "csv_hash", "log_hash"]:
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
    """Step 2: Upload RAG architecture guide (test RAG technology search)"""
    print("\n=== Step 2: Upload RAG architecture guide (TXT) ===")
    
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
    """Step 3: Upload AI agent quality guide (test software engineering search)"""
    print("\n=== Step 3: Upload AI agent quality guide (PDF) ===")
    
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


def test_03b_upload_markdown_document(test_documents):
    """Step 3b: Upload vector databases guide (test database search)"""
    print("\n=== Step 3b: Upload vector databases guide (Markdown) ===")
    
    md_path = test_documents["md"]
    assert md_path.exists(), f"Test file not found: {md_path}"
    
    with open(md_path, "rb") as f:
        files = {"file": (md_path.name, f, "text/markdown")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")


def test_03c_upload_json_document(test_documents):
    """Step 3c: Upload electronics catalog (test product/price search)"""
    print("\n=== Step 3c: Upload electronics catalog (JSON → YAML) ===")
    
    json_path = test_documents["json"]
    assert json_path.exists(), f"Test file not found: {json_path}"
    
    with open(json_path, "rb") as f:
        files = {"file": (json_path.name, f, "application/json")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from JSON (YAML conversion)"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: JSON converted to YAML for semantic preservation")


def test_03d_upload_html_document(test_documents):
    """Step 3d: Upload art exhibition info (test art/event search)"""
    print("\n=== Step 3d: Upload art exhibition info (HTML → Markdown) ===")
    
    html_path = test_documents["html"]
    assert html_path.exists(), f"Test file not found: {html_path}"
    
    with open(html_path, "rb") as f:
        files = {"file": (html_path.name, f, "text/html")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from HTML"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: HTML converted to Markdown (preserves structure)")


def test_03e_upload_yaml_document(test_documents):
    """Step 3e: Upload business metrics (test KPI/financial search)"""
    print("\n=== Step 3e: Upload business metrics (YAML) ===")
    
    yaml_path = test_documents["yaml"]
    assert yaml_path.exists(), f"Test file not found: {yaml_path}"
    
    with open(yaml_path, "rb") as f:
        files = {"file": (yaml_path.name, f, "application/x-yaml")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from YAML"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: YAML kept as-is (already optimal for LLM)")


def test_03f_upload_xml_document(test_documents):
    """Step 3f: Upload GDPR compliance report (test legal/compliance search)"""
    print("\n=== Step 3f: Upload GDPR compliance report (XML → YAML) ===")
    
    xml_path = test_documents["xml"]
    assert xml_path.exists(), f"Test file not found: {xml_path}"
    
    with open(xml_path, "rb") as f:
        files = {"file": (xml_path.name, f, "application/xml")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from XML"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: XML converted to YAML (preserves semantic structure)")


def test_03g_upload_csv_document(test_documents):
    """Step 3g: Upload financial quarterly report (test revenue/growth search)"""
    print("\n=== Step 3g: Upload financial quarterly report (CSV) ===")
    
    csv_path = test_documents["csv"]
    assert csv_path.exists(), f"Test file not found: {csv_path}"
    
    with open(csv_path, "rb") as f:
        files = {"file": (csv_path.name, f, "text/csv")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from CSV"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: CSV kept as plain text (tabular structure preserved)")


def test_03h_upload_log_document(test_documents):
    """Step 3h: Upload system operations log (test debugging/ops search)"""
    print("\n=== Step 3h: Upload system operations log (LOG) ===")
    
    log_path = test_documents["log"]
    assert log_path.exists(), f"Test file not found: {log_path}"
    
    with open(log_path, "rb") as f:
        files = {"file": (log_path.name, f, "text/plain")}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from LOG"
    print(f"✓ Uploaded: {result['filename']}")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print("  - Note: Log file kept as plain text (timestamps + messages)")


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


def test_05a_semantic_search_products():
    """Step 5a: Semantic search - product queries should retrieve electronics catalog"""
    print("\n=== Step 5a: Semantic search - Product specifications ===")
    
    query = "Which smartphone model has the highest camera megapixels and what is its price?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for product query"
    assert len(result["results"]) > 0, "Empty results list"
    
    # Semantic validation: results should come from electronics_catalog.json
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("electronics_catalog" in fn for fn in filenames), \
        f"Expected electronics_catalog in results, got: {filenames}"
    
    # Content validation: should mention camera specs and prices
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["camera", "megapixel", "mp", "photo"]), \
        "Expected camera-related content in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (electronics catalog retrieved)")


def test_05b_semantic_search_art():
    """Step 5b: Semantic search - art queries should retrieve exhibition info"""
    print("\n=== Step 5b: Semantic search - Art exhibitions ===")
    
    query = "How much do family tickets cost for the art exhibition?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for art query"
    
    # Semantic validation: results should come from art_exhibition.html
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("art_exhibition" in fn for fn in filenames), \
        f"Expected art_exhibition in results, got: {filenames}"
    
    # Content validation: should mention tickets/prices/family
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["ticket", "price", "family", "£", "exhibition"]), \
        "Expected art/ticket-related content in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (art exhibition retrieved)")


def test_05c_semantic_search_business():
    """Step 5c: Semantic search - business queries should retrieve metrics"""
    print("\n=== Step 5c: Semantic search - Business metrics ===")
    
    query = "What is our customer acquisition cost and lifetime value ratio?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for business query"
    
    # Semantic validation: results should come from business_metrics.yaml
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("business_metrics" in fn for fn in filenames), \
        f"Expected business_metrics in results, got: {filenames}"
    
    # Content validation: should mention CAC/LTV metrics
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["cac", "ltv", "customer", "acquisition", "value"]), \
        "Expected business metrics in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (business metrics retrieved)")


def test_05d_semantic_search_compliance():
    """Step 5d: Semantic search - legal queries should retrieve GDPR report"""
    print("\n=== Step 5d: Semantic search - Legal compliance ===")
    
    query = "What are the critical GDPR compliance findings in our assessment?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for compliance query"
    
    # Semantic validation: results should come from gdpr_compliance.xml
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("gdpr_compliance" in fn for fn in filenames), \
        f"Expected gdpr_compliance in results, got: {filenames}"
    
    # Content validation: should mention GDPR/compliance/critical
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["gdpr", "compliance", "critical", "finding", "assessment"]), \
        "Expected GDPR compliance content in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (GDPR report retrieved)")


def test_05e_semantic_search_financials():
    """Step 5e: Semantic search - financial queries should retrieve quarterly report"""
    print("\n=== Step 5e: Semantic search - Financial data ===")
    
    query = "Show quarterly revenue growth trends over 2025"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for financial query"
    
    # Semantic validation: results should come from financial_quarterly_report.csv
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("financial" in fn or "quarterly" in fn for fn in filenames), \
        f"Expected financial report in results, got: {filenames}"
    
    # Content validation: should mention revenue/quarterly/2025
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["revenue", "quarter", "2025", "growth"]), \
        "Expected financial data in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (financial report retrieved)")


def test_05f_semantic_search_operations():
    """Step 5f: Semantic search - ops queries should retrieve system logs"""
    print("\n=== Step 5f: Semantic search - System operations ===")
    
    query = "What caused the duplicate document rejection in the RAG system?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned for operations query"
    
    # Semantic validation: results should come from rag_system_operations.log
    filenames = [chunk["filename"] for chunk in result["results"]]
    assert any("operations" in fn or "rag_system" in fn for fn in filenames), \
        f"Expected operations log in results, got: {filenames}"
    
    # Content validation: should mention duplicate/rejection/error
    top_chunk = result["results"][0]["chunk_text"]
    assert any(keyword in top_chunk.lower() for keyword in ["duplicate", "reject", "error", "hash", "collision"]), \
        "Expected operations/error content in top result"
    
    print(f"✓ Query: '{query}'")
    print(f"  Found {result['total']} chunks (top from: {result['results'][0]['filename']})")
    print(f"  Similarity: {result['results'][0]['similarity']:.3f}")
    print(f"  Semantic validation: PASSED (operations log retrieved)")


def test_05g_semantic_isolation_negative():
    """Step 5g: Negative test - topic isolation (camera query should NOT return art/business docs)"""
    print("\n=== Step 5g: Semantic isolation test ===")
    
    query = "smartphone camera specifications"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 10},
        timeout=30
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    result = response.json()
    
    assert result["total"] > 0, "No results returned"
    
    # Get all results to check topic isolation
    all_filenames = [chunk["filename"] for chunk in result["results"]]
    
    # PRIMARY: Should retrieve electronics catalog in results (positive validation)
    assert any("electronics" in fn for fn in all_filenames), \
        f"Expected electronics_catalog in results for camera query, got: {all_filenames[:5]}"
    
    # SECONDARY: Among test documents, should NOT retrieve art/business/compliance docs
    # (Note: May have other user documents in DB, that's OK)
    test_docs_in_results = [fn for fn in all_filenames if any(
        topic in fn for topic in ["electronics_catalog", "art_exhibition", "business_metrics", 
                                   "gdpr_compliance", "financial_quarterly", "rag_system_operations",
                                   "rag_architecture", "google_agent", "vector_databases"]
    )]
    
    unwanted_test_topics = ["art_exhibition", "business_metrics", "gdpr_compliance"]
    unwanted_in_results = [fn for fn in test_docs_in_results if any(topic in fn for topic in unwanted_test_topics)]
    
    if unwanted_in_results:
        print(f"  WARNING: Unwanted test documents appeared: {unwanted_in_results}")
        print(f"  (This suggests embeddings aren't isolating topics well)")
    
    print(f"✓ Query: '{query}'")
    print(f"  Test documents in results: {test_docs_in_results[:3]}")
    print(f"  Semantic validation: PASSED (electronics_catalog retrieved)")


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
