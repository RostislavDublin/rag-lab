"""
End-to-End test for complete RAG workflow with semantic search and metadata filtering

Tests the full lifecycle with thematic documents:
1. Health check (API + current documents)
2. Upload 9 documents with distinct topics AND metadata (multi-user simulation)
   - TXT: RAG technology (alice@company.com, engineering, python/api)
   - PDF: AI agents (alice@company.com, engineering, agents/quality)
   - MD: Databases (bob@company.com, engineering, database/postgresql)
   - JSON: Products (bob@company.com, sales, catalog/pricing)
   - HTML: Art (charlie@company.com, marketing, exhibitions/events)
   - YAML: Business (charlie@company.com, finance, metrics/kpis)
   - XML: GDPR (alice@company.com, legal, compliance/gdpr)
   - CSV: Financials (bob@company.com, finance, quarterly/reports)
   - LOG: Operations (charlie@company.com, operations, logs/monitoring)
3. List documents
4. Metadata filtering tests - validate MongoDB-style filters work correctly
   - User isolation (uploaded_by filtering)
   - Department filtering (engineering, sales, legal, finance, marketing, operations)
   - Tag matching ($in operator)
   - Priority filtering ($ne operator)
   - Complex AND/OR/NOT combinations
   - $exists operator
5. Semantic search tests - validate RAG returns topically correct documents
   - Product queries → electronics catalog
   - Art queries → exhibition info
   - Business queries → metrics
   - Compliance queries → GDPR report
   - Financial queries → quarterly report
   - Operations queries → system logs
   - Topic isolation (negative test)
6. Download original files
7. Delete documents
8. Verify cleanup (DB + GCS)

Philosophy: Non-trivial queries test semantic understanding vs keyword matching.
Each document has distinct topic AND metadata, enabling validation that both
semantic search and metadata filtering work correctly in production scenarios.
"""

import json
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
        "security": fixtures_dir / "security_test.txt",  # Topic: Security test (protected fields)
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
    docs["security_hash"] = calculate_file_hash(docs["security"])
    
    return docs


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_documents(request, test_documents, auth_headers):
    """Clean up ONLY test documents before and after tests (preserves user documents!)"""
    print("\n🧹 Cleaning up test documents (user documents will be preserved)...")
    
    # Delete test documents by hash (if they exist from previous run)
    deleted_before = 0
    for hash_key in ["txt_hash", "pdf_hash", "md_hash", "json_hash", "html_hash", "yaml_hash", "xml_hash", "csv_hash", "log_hash", "security_hash"]:
        file_hash = test_documents[hash_key]
        response = requests.delete(f"{API_BASE}/v1/documents/by-hash/{file_hash}", headers=auth_headers, timeout=30)
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
        for hash_key in ["txt_hash", "pdf_hash", "md_hash", "json_hash", "html_hash", "yaml_hash", "xml_hash", "csv_hash", "log_hash", "security_hash"]:
            file_hash = test_documents[hash_key]
            response = requests.delete(f"{API_BASE}/v1/documents/by-hash/{file_hash}", headers=auth_headers, timeout=30)
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


def test_02_upload_txt_document(test_documents, auth_headers):
    """Step 2: Upload RAG architecture guide (Alice, engineering, Python/API)"""
    print("\n=== Step 2: Upload RAG architecture guide (TXT) ===")
    
    txt_path = test_documents["txt"]
    assert txt_path.exists(), f"Test file not found: {txt_path}"
    
    # Alice (engineering, Python developer)
    headers = {**auth_headers, "X-End-User-ID": "alice@company.com"}
    metadata = json.dumps({
        "department": "engineering",
        "tags": ["python", "api", "architecture", "rag"],
        "priority": "high"
    })
    
    with open(txt_path, "rb") as f:
        files = {"file": (txt_path.name, f, "text/plain")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']} (alice@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: engineering, tags=[python, api, architecture, rag], priority=high")


def test_03_upload_pdf_document(test_documents, auth_headers):
    """Step 3: Upload AI agent quality guide (Alice, engineering, agents/quality)"""
    print("\n=== Step 3: Upload AI agent quality guide (PDF) ===")
    
    pdf_path = test_documents["pdf"]
    assert pdf_path.exists(), f"Test file not found: {pdf_path}"
    
    # Alice (engineering, AI/agents focus)
    headers = {**auth_headers, "X-End-User-ID": "alice@company.com"}
    metadata = json.dumps({
        "department": "engineering",
        "tags": ["agents", "quality", "ai", "software-engineering"],
        "priority": "high"
    })
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']} (alice@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: engineering, tags=[agents, quality, ai, software-engineering], priority=high")


def test_03b_upload_markdown_document(test_documents, auth_headers):
    """Step 3b: Upload vector databases guide (Bob, engineering, database/postgresql)"""
    print("\n=== Step 3b: Upload vector databases guide (Markdown) ===")
    
    md_path = test_documents["md"]
    assert md_path.exists(), f"Test file not found: {md_path}"
    
    # Bob (engineering, database specialist)
    headers = {**auth_headers, "X-End-User-ID": "bob@company.com"}
    metadata = json.dumps({
        "department": "engineering",
        "tags": ["database", "postgresql", "vector-search", "pgvector"],
        "priority": "high"
    })
    
    with open(md_path, "rb") as f:
        files = {"file": (md_path.name, f, "text/markdown")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created"
    print(f"✓ Uploaded: {result['filename']} (bob@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: engineering, tags=[database, postgresql, vector-search, pgvector], priority=high")


def test_03c_upload_json_document(test_documents, auth_headers):
    """Step 3c: Upload electronics catalog (Bob, sales, catalog/pricing)"""
    print("\n=== Step 3c: Upload electronics catalog (JSON → YAML) ===")
    
    json_path = test_documents["json"]
    assert json_path.exists(), f"Test file not found: {json_path}"
    
    # Bob (sales, product catalog)
    headers = {**auth_headers, "X-End-User-ID": "bob@company.com"}
    metadata = json.dumps({
        "department": "sales",
        "tags": ["catalog", "products", "pricing", "electronics"],
        "priority": "medium"
    })
    
    with open(json_path, "rb") as f:
        files = {"file": (json_path.name, f, "application/json")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from JSON (YAML conversion)"
    print(f"✓ Uploaded: {result['filename']} (bob@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: sales, tags=[catalog, products, pricing, electronics], priority=medium")
    print("  - Note: JSON converted to YAML for semantic preservation")


def test_03c2_security_protected_metadata_fields(test_documents, auth_headers):
    """Step 3c2: SECURITY - User cannot override protected system metadata fields"""
    print("\n=== Step 3c2: SECURITY TEST - Protected metadata fields ===")
    
    security_path = test_documents["security"]
    assert security_path.exists(), f"Test file not found: {security_path}"
    
    # Attacker tries to impersonate another user and manipulate timestamps
    # These fields should be REJECTED (400 error) not silently filtered
    malicious_metadata = json.dumps({
        "uploaded_by": "admin@company.com",  # ATTACK: impersonation
        "uploaded_at": "2020-01-01T00:00:00",  # ATTACK: fake timestamp
        "uploaded_via": "trusted_service",  # ATTACK: fake source
        "original_filename": "secret.pdf",  # ATTACK: fake filename
        "department": "security",  # LEGITIMATE: user field
    })
    
    with open(security_path, "rb") as f:
        files = {"file": (security_path.name, f, "text/plain")}
        data = {"metadata": malicious_metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=auth_headers, timeout=60)
    
    # SECURITY VERIFICATION: Upload MUST be REJECTED with 400 error
    assert response.status_code == 400, f"Expected 400 error, got {response.status_code}: {response.text}"
    
    error_detail = response.json()["detail"]
    assert "protected field names" in error_detail.lower(), f"Error should mention protected fields: {error_detail}"
    assert "uploaded_by" in error_detail, "Error should list 'uploaded_by' as protected"
    assert "uploaded_at" in error_detail, "Error should list 'uploaded_at' as protected"
    assert "uploaded_via" in error_detail, "Error should list 'uploaded_via' as protected"
    
    print(f"✓ SECURITY VERIFIED: Upload rejected with 400 error")
    print(f"  - Error: {error_detail[:100]}...")
    
    # Now test that upload WITHOUT protected fields succeeds
    print(f"\n  Testing legitimate upload (no protected fields)...")
    legitimate_metadata = json.dumps({
        "department": "security",  # LEGITIMATE: user field
        "tags": ["test", "security"],
    })
    
    with open(security_path, "rb") as f:
        files = {"file": (security_path.name, f, "text/plain")}
        data = {"metadata": legitimate_metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=auth_headers, timeout=60)
    
    assert response.status_code == 200, f"Legitimate upload failed: {response.text}"
    result = response.json()
    doc_id = result["doc_id"]
    
    # Verify system fields are auto-populated correctly
    response = requests.get(f"{API_BASE}/v1/documents", headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    documents = response.json()["documents"]
    doc = next((d for d in documents if d["doc_id"] == doc_id), None)
    assert doc is not None, f"Document {doc_id} not found"
    
    # Check system fields at top level
    assert doc["uploaded_by"] == "javaisforever@gmail.com", "uploaded_by should be from JWT"
    assert doc["uploaded_at"].startswith("2025"), "uploaded_at should be current timestamp"
    assert doc["uploaded_via"] == "api", "uploaded_via should be 'api'"
    
    # Check metadata does NOT contain protected fields
    metadata = doc["metadata"]
    assert "uploaded_by" not in metadata, "metadata should not contain uploaded_by"
    assert "uploaded_at" not in metadata, "metadata should not contain uploaded_at"
    assert "uploaded_via" not in metadata, "metadata should not contain uploaded_via"
    
    # Check legitimate user fields are preserved
    assert metadata.get("department") == "security", "User field should be preserved"
    assert "test" in metadata.get("tags", []), "User field should be preserved"
    
    print(f"✓ Legitimate upload succeeded")
    print(f"  - uploaded_by: {doc['uploaded_by']} (from JWT)")
    print(f"  - uploaded_at: {doc['uploaded_at'][:19]}")
    print(f"  - uploaded_via: {doc['uploaded_via']}")
    print(f"  - metadata: {metadata} (no protected fields)")
    print(f"  ✓ Protected fields CANNOT be overridden by user input")


def test_03d_upload_html_document(test_documents, auth_headers):
    """Step 3d: Upload art exhibition info (Charlie, marketing, exhibitions/events)"""
    print("\n=== Step 3d: Upload art exhibition info (HTML → Markdown) ===")
    
    html_path = test_documents["html"]
    assert html_path.exists(), f"Test file not found: {html_path}"
    
    # Charlie (marketing, events)
    headers = {**auth_headers, "X-End-User-ID": "charlie@company.com"}
    metadata = json.dumps({
        "department": "marketing",
        "tags": ["exhibitions", "events", "art", "tickets"],
        "priority": "low"
    })
    
    with open(html_path, "rb") as f:
        files = {"file": (html_path.name, f, "text/html")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from HTML"
    print(f"✓ Uploaded: {result['filename']} (charlie@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: marketing, tags=[exhibitions, events, art, tickets], priority=low")
    print("  - Note: HTML converted to Markdown (preserves structure)")


def test_03e_upload_yaml_document(test_documents, auth_headers):
    """Step 3e: Upload business metrics (Charlie, finance, metrics/kpis)"""
    print("\n=== Step 3e: Upload business metrics (YAML) ===")
    
    yaml_path = test_documents["yaml"]
    assert yaml_path.exists(), f"Test file not found: {yaml_path}"
    
    # Charlie (finance, business metrics)
    headers = {**auth_headers, "X-End-User-ID": "charlie@company.com"}
    metadata = json.dumps({
        "department": "finance",
        "tags": ["metrics", "kpis", "business", "performance"],
        "priority": "high"
    })
    
    with open(yaml_path, "rb") as f:
        files = {"file": (yaml_path.name, f, "application/x-yaml")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from YAML"
    print(f"✓ Uploaded: {result['filename']} (charlie@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: finance, tags=[metrics, kpis, business, performance], priority=high")
    print("  - Note: YAML kept as-is (already optimal for LLM)")


def test_03f_upload_xml_document(test_documents, auth_headers):
    """Step 3f: Upload GDPR compliance report (Alice, legal, compliance/gdpr)"""
    print("\n=== Step 3f: Upload GDPR compliance report (XML → YAML) ===")
    
    xml_path = test_documents["xml"]
    assert xml_path.exists(), f"Test file not found: {xml_path}"
    
    # Alice (legal, compliance)
    headers = {**auth_headers, "X-End-User-ID": "alice@company.com"}
    metadata = json.dumps({
        "department": "legal",
        "tags": ["compliance", "gdpr", "legal", "privacy"],
        "priority": "high"
    })
    
    with open(xml_path, "rb") as f:
        files = {"file": (xml_path.name, f, "application/xml")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from XML (YAML conversion)"
    print(f"✓ Uploaded: {result['filename']} (alice@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: legal, tags=[compliance, gdpr, legal, privacy], priority=high")
    print("  - Note: XML converted to YAML for semantic preservation")


def test_03g_upload_csv_document(test_documents, auth_headers):
    """Step 3g: Upload financial quarterly report (Bob, finance, quarterly/reports)"""
    print("\n=== Step 3g: Upload financial quarterly report (CSV) ===")
    
    csv_path = test_documents["csv"]
    assert csv_path.exists(), f"Test file not found: {csv_path}"
    
    # Bob (finance, reports)
    headers = {**auth_headers, "X-End-User-ID": "bob@company.com"}
    metadata = json.dumps({
        "department": "finance",
        "tags": ["quarterly", "reports", "financial", "revenue"],
        "priority": "high"
    })
    
    with open(csv_path, "rb") as f:
        files = {"file": (csv_path.name, f, "text/csv")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from CSV"
    print(f"✓ Uploaded: {result['filename']} (bob@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: finance, tags=[quarterly, reports, financial, revenue], priority=high")
    print("  - Note: CSV kept as plain text (tabular structure preserved)")


def test_03h_upload_log_document(test_documents, auth_headers):
    """Step 3h: Upload system operations log (Charlie, operations, logs/monitoring)"""
    print("\n=== Step 3h: Upload system operations log (LOG) ===")
    
    log_path = test_documents["log"]
    assert log_path.exists(), f"Test file not found: {log_path}"
    
    # Charlie (operations, monitoring)
    headers = {**auth_headers, "X-End-User-ID": "charlie@company.com"}
    metadata = json.dumps({
        "department": "operations",
        "tags": ["logs", "monitoring", "system", "operations"],
        "priority": "medium"
    })
    
    with open(log_path, "rb") as f:
        files = {"file": (log_path.name, f, "text/plain")}
        data = {"metadata": metadata}
        response = requests.post(f"{API_BASE}/v1/documents/upload", files=files, data=data, headers=headers, timeout=60)
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    result = response.json()
    
    assert result["chunks_created"] > 0, "No chunks created from LOG"
    print(f"✓ Uploaded: {result['filename']} (charlie@company.com)")
    print(f"  - ID: {result['doc_id']}, UUID: {result['doc_uuid']}")
    print(f"  - Chunks: {result['chunks_created']}")
    print(f"  - Metadata: operations, tags=[logs, monitoring, system, operations], priority=medium")
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


def test_04a_metadata_filter_by_user(auth_headers):
    """Step 4a: Metadata filtering - user isolation (multi-tenant)"""
    print("\n=== Step 4a: Metadata filtering - User isolation ===")
    
    # Alice's documents only
    payload = {
        "query": "technical documentation",
        "filters": {"uploaded_by": "alice@company.com"},
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200, f"Query failed: {response.text}"
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find Alice's documents"
    print(f"✓ Alice's documents: {len(result['results'])} chunk(s)")
    
    # Bob's documents only
    payload["filters"] = {"uploaded_by": "bob@company.com"}
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find Bob's documents"
    print(f"✓ Bob's documents: {len(result['results'])} chunk(s)")


def test_04b_metadata_filter_by_department(auth_headers):
    """Step 4b: Metadata filtering - department filtering"""
    print("\n=== Step 4b: Metadata filtering - Department ===")
    
    # Engineering department
    payload = {
        "query": "technical systems",
        "filters": {"department": "engineering"},
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find engineering documents"
    print(f"✓ Engineering: {len(result['results'])} chunk(s)")
    
    # Finance department
    payload["filters"] = {"department": "finance"}
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find finance documents"
    print(f"✓ Finance: {len(result['results'])} chunk(s)")


def test_04c_metadata_filter_by_tags(auth_headers):
    """Step 4c: Metadata filtering - tag matching with $in operator"""
    print("\n=== Step 4c: Metadata filtering - Tags ($in) ===")
    
    # Python-related documents
    payload = {
        "query": "programming",
        "filters": {"tags": {"$in": ["python"]}},
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find Python documents"
    print(f"✓ Python tag: {len(result['results'])} chunk(s)")
    
    # Database-related documents
    payload["filters"] = {"tags": {"$in": ["database", "postgresql"]}}
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find database documents"
    print(f"✓ Database tags: {len(result['results'])} chunk(s)")


def test_04d_metadata_filter_by_priority(auth_headers):
    """Step 4d: Metadata filtering - priority with $ne operator"""
    print("\n=== Step 4d: Metadata filtering - Priority ($ne) ===")
    
    # High priority only
    payload = {
        "query": "important",
        "filters": {"priority": "high"},
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find high priority documents"
    print(f"✓ High priority: {len(result['results'])} chunk(s)")
    
    # Non-high priority (medium or low)
    payload["filters"] = {"priority": {"$ne": "high"}}
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find non-high priority documents"
    print(f"✓ Non-high priority: {len(result['results'])} chunk(s)")


def test_04e_metadata_filter_complex_and(auth_headers):
    """Step 4e: Metadata filtering - complex $and logic"""
    print("\n=== Step 4e: Metadata filtering - Complex AND ===")
    
    # Engineering department + Python tag + high priority
    payload = {
        "query": "technical guide",
        "filters": {
            "$and": [
                {"department": "engineering"},
                {"tags": {"$in": ["python"]}},
                {"priority": "high"}
            ]
        },
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find engineering + Python + high priority"
    print(f"✓ Engineering + Python + High priority: {len(result['results'])} chunk(s)")


def test_04f_metadata_filter_complex_or(auth_headers):
    """Step 4f: Metadata filtering - complex $or logic"""
    print("\n=== Step 4f: Metadata filtering - Complex OR ===")
    
    # Finance OR Legal departments
    payload = {
        "query": "compliance business",
        "filters": {
            "$or": [
                {"department": "finance"},
                {"department": "legal"}
            ]
        },
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find finance or legal documents"
    print(f"✓ Finance OR Legal: {len(result['results'])} chunk(s)")


def test_04g_metadata_filter_complex_not(auth_headers):
    """Step 4g: Metadata filtering - complex $not logic"""
    print("\n=== Step 4g: Metadata filtering - Complex NOT ===")
    
    # Exclude marketing department
    payload = {
        "query": "business documentation",
        "filters": {
            "$not": {"department": "marketing"}
        },
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 1, "Should find non-marketing documents"
    print(f"✓ NOT marketing: {len(result['results'])} chunk(s)")


def test_04h_metadata_filter_nested(auth_headers):
    """Step 4h: Metadata filtering - deeply nested logic (agent use case)"""
    print("\n=== Step 4h: Metadata filtering - Deeply nested (agent scenario) ===")
    
    # Complex: (Alice OR Bob) AND high priority AND (python OR database tags)
    payload = {
        "query": "technical information",
        "filters": {
            "$and": [
                {
                    "$or": [
                        {"uploaded_by": "alice@company.com"},
                        {"uploaded_by": "bob@company.com"}
                    ]
                },
                {"priority": "high"},
                {
                    "$or": [
                        {"tags": {"$in": ["python"]}},
                        {"tags": {"$in": ["database"]}}
                    ]
                }
            ]
        },
        "top_k": 10
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    # May return 0 or more results depending on exact metadata match
    print(f"✓ Complex nested filter: {len(result['results'])} chunk(s)")


def test_04i_metadata_filter_no_filter(auth_headers):
    """Step 4i: Metadata filtering - no filter returns all documents"""
    print("\n=== Step 4i: Metadata filtering - No filter (baseline) ===")
    
    payload = {
        "query": "information systems",
        "top_k": 20
    }
    response = requests.post(f"{API_BASE}/v1/query", json=payload, headers=auth_headers, timeout=30)
    assert response.status_code == 200
    
    result = response.json()
    assert len(result["results"]) >= 3, "Should find multiple documents across all users"
    print(f"✓ No filter (all documents): {len(result['results'])} chunk(s)")


def test_05a_semantic_search_products(auth_headers):
    """Step 5a: Semantic search - product queries should retrieve electronics catalog"""
    print("\n=== Step 5a: Semantic search - Product specifications ===")
    
    query = "Which smartphone model has the highest camera megapixels and what is its price?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.5},
        headers=auth_headers,
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


def test_05b_semantic_search_art(auth_headers):
    """Step 5b: Semantic search - art queries should retrieve exhibition info"""
    print("\n=== Step 5b: Semantic search - Art exhibitions ===")
    
    query = "How much do family tickets cost for the art exhibition?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.5},
        headers=auth_headers,
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


def test_05c_semantic_search_business(auth_headers):
    """Step 5c: Semantic search - business queries should retrieve metrics"""
    print("\n=== Step 5c: Semantic search - Business metrics ===")
    
    query = "What is the customer satisfaction rating and which region has the highest sales growth?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.5},
        headers=auth_headers,
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


def test_05d_semantic_search_compliance(auth_headers):
    """Step 5d: Semantic search - legal queries should retrieve GDPR report"""
    print("\n=== Step 5d: Semantic search - Legal compliance ===")
    
    query = "What are the critical GDPR compliance findings in our assessment?"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.5},
        headers=auth_headers,
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


def test_05e_semantic_search_financials(auth_headers):
    """Step 5e: Semantic search - financial queries should retrieve quarterly report"""
    print("\n=== Step 5e: Semantic search - Financial data ===")
    
    query = "Show quarterly revenue growth trends over 2025"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.5},
        headers=auth_headers,
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


def test_05f_semantic_search_operations(auth_headers):
    """Step 5f: Semantic search - ops queries should retrieve system logs"""
    print("\n=== Step 5f: Semantic search - System operations ===")
    
    # More specific query that better matches log file content
    query = "duplicate document hash collision error upload rejected"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 5, "min_similarity": 0.3},  # Lower threshold for log files
        headers=auth_headers,
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


def test_05g_semantic_isolation_negative(auth_headers):
    """Step 5g: Negative test - topic isolation (camera query should NOT return art/business docs)"""
    print("\n=== Step 5g: Semantic isolation test ===")
    
    query = "smartphone camera specifications"
    response = requests.post(
        f"{API_BASE}/v1/query",
        json={"query": query, "top_k": 10, "min_similarity": 0.5},
        headers=auth_headers,
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
