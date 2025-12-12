"""Test extraction from real fixture files"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from src.document_processor import DocumentProcessor, EmbeddingProvider


@pytest.fixture
def processor():
    # Create mock genai client (only needed for embedding, not text extraction)
    mock_client = Mock()
    return DocumentProcessor(
        embedding_provider=EmbeddingProvider.VERTEX_AI,
        genai_client=mock_client
    )


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent.parent / "fixtures" / "documents"


def test_json_fixture_extraction(processor):
    """Test extraction from JSON - verifies conversion to clean YAML"""
    json_content = b"""{
  "title": "Machine Learning Best Practices",
  "author": "AI Research Team",
  "sections": [
    {
      "heading": "Data Preparation",
      "content": "Clean your data thoroughly. Remove duplicates, handle missing values, and normalize features."
    },
    {
      "heading": "Model Selection",
      "content": "Start with simple models. Use cross-validation to evaluate performance."
    }
  ],
  "tags": ["machine-learning", "best-practices", "data-science"]
}"""
    
    text = processor.extract_text(json_content, '.json')
    
    # Check extracted content
    assert 'Machine Learning Best Practices' in text
    assert 'Data Preparation' in text
    assert 'Clean your data thoroughly' in text
    assert 'cross-validation' in text
    
    # Verify smart parsing (no JSON syntax)
    assert '{' not in text
    assert '"title"' not in text
    
    print(f"\n=== Extracted JSON ({len(text)} chars) ===")
    print(text[:500])


def test_xml_fixture_extraction(processor):
    """Test extraction from XML - verifies conversion to clean YAML"""
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<documentation>
  <article id="rag-101">
    <title>Introduction to Retrieval Augmented Generation</title>
    <author>
      <name>Dr. Sarah Chen</name>
      <affiliation>AI Institute</affiliation>
    </author>
    <abstract>
      RAG combines retrieval systems with language models to provide grounded, 
      factual responses. This approach reduces hallucinations and enables LLMs 
      to access up-to-date information.
    </abstract>
    <section>
      <heading>Core Components</heading>
      <paragraph>
        A RAG system consists of three main parts: a document store, 
        an embedding model, and a language model.
      </paragraph>
    </section>
    <references>
      <reference>Lewis et al. 2020. Retrieval-Augmented Generation</reference>
    </references>
  </article>
</documentation>"""
    
    text = processor.extract_text(xml_content, '.xml')
    
    # Check extracted content
    assert 'Retrieval Augmented Generation' in text
    assert 'Dr. Sarah Chen' in text
    assert 'reduces hallucinations' in text or 'Reduces hallucinations' in text
    assert 'Lewis et al' in text
    
    # Verify smart parsing (no XML tags)
    assert '<article' not in text
    assert '<title>' not in text
    assert 'encoding="UTF-8"' not in text
    
    print(f"\n=== Extracted XML ({len(text)} chars) ===")
    print(text[:500])


def test_markdown_fixture_extraction(processor, fixtures_dir):
    """Test extraction from vector_databases.md fixture"""
    md_file = fixtures_dir / "vector_databases.md"
    
    with open(md_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.md')
    
    # Check extracted content
    assert 'Vector Databases for RAG Systems' in text
    assert 'pgvector' in text
    assert 'Pinecone' in text
    assert 'Weaviate' in text
    assert 'import asyncpg' in text
    
    # Markdown is kept as-is (including markup)
    assert '##' in text  # Headers preserved
    assert '```python' in text  # Code blocks preserved
    
    print(f"\n=== Extracted Markdown ({len(text)} chars) ===")
    print(text[:500])


def test_all_formats_produce_searchable_text(processor, fixtures_dir):
    """Verify all formats produce clean, searchable text for RAG"""
    
    # Test inline formats
    inline_formats = {
        'json': b'{"title": "Test", "content": "Machine learning data"}',
        'xml': b'<?xml version="1.0"?><doc><title>Test</title><content>RAG system info</content></doc>',
        'csv': b'product,price\nLaptop,999\nMouse,25',
        'yaml': b'name: test\nversion: 1.0\ndescription: Test config',
    }
    
    for fmt, content in inline_formats.items():
        text = processor.extract_text(content, f'.{fmt}')
        assert len(text) > 20, f"{fmt} produced too little text"
        assert text.isprintable() or '\n' in text, f"{fmt} produced non-printable text"
        print(f"{fmt.upper()}: {len(text)} chars extracted")
    
    # Test shared fixtures (still files in fixtures/)
    shared_formats = {
        'md': 'vector_databases.md',
        'log': 'rag_system_operations.log',
    }
    
    for fmt, filename in shared_formats.items():
        file_path = fixtures_dir / filename
        with open(file_path, 'rb') as f:
            content = f.read()
        text = processor.extract_text(content, f'.{fmt}')
        assert len(text) > 100, f"{fmt} produced too little text"
        print(f"{fmt.upper()}: {len(text)} chars extracted")


def test_csv_fixture_extraction(processor):
    """Test extraction from CSV - verifies plain text preservation"""
    csv_content = b"""product,price,stock,category
Laptop,999,15,Electronics
Mouse,25,150,Accessories
Keyboard,75,80,Accessories
Monitor,350,25,Electronics
Webcam,120,45,Electronics"""
    
    text = processor.extract_text(csv_content, '.csv')
    
    # Check CSV content preserved
    assert 'product,price,stock,category' in text  # Header
    assert 'Laptop' in text
    assert '999' in text
    assert 'Electronics' in text
    
    # CSV kept as plain text (good for RAG - readable structure)
    print(f"\n=== Extracted CSV ({len(text)} chars) ===")
    print(text[:200])


def test_yaml_fixture_extraction(processor):
    """Test extraction from YAML - verifies kept as-is (optimal for LLM)"""
    yaml_content = b"""name: rag-lab
version: 0.2.0
description: RAG-as-a-Service with multi-format support

dependencies:
  python: ">=3.10"
  packages:
    - fastapi>=0.109.0
    - google-cloud-aiplatform>=1.38.0
    - psycopg2-binary>=2.9.9
    - pgvector>=0.2.3

features:
  pdf_processing: true
  vector_search: true

database:
  type: PostgreSQL
  extensions:
    - pgvector
  connection_pool: 5-20"""
    
    text = processor.extract_text(yaml_content, '.yaml')
    
    # Check YAML content preserved
    assert 'rag-lab' in text
    assert 'version:' in text or 'version :' in text
    assert 'fastapi' in text
    assert 'PostgreSQL' in text
    
    # YAML kept as-is (already optimal for LLM)
    assert 'dependencies:' in text
    
    print(f"\n=== Extracted YAML ({len(text)} chars) ===")
    print(text[:300])


def test_log_fixture_extraction(processor, fixtures_dir):
    """Test extraction from rag_system_operations.log fixture"""
    log_file = fixtures_dir / "rag_system_operations.log"
    
    with open(log_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.log')
    
    # Check log content preserved
    assert '2025-12-11' in text  # Timestamps
    assert 'INFO' in text  # Log levels
    assert 'RAG API server' in text  # Server startup
    assert 'ERROR' in text  # Error messages
    
    # Logs kept as plain text (timestamps + messages useful for RAG)
    print(f"\n=== Extracted Log ({len(text)} chars) ===")
    print(text[:300])


def test_html_fixture_extraction(processor):
    """Test extraction from HTML - verifies conversion to Markdown"""
    html_content = b"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>RAG System Documentation</title>
</head>
<body>
    <h1>RAG System Overview</h1>
    
    <p>A <strong>Retrieval-Augmented Generation</strong> (RAG) system combines 
    information retrieval with large language models.</p>
    
    <h2>Key Components</h2>
    
    <ul>
        <li><strong>Document Store:</strong> PostgreSQL with pgvector extension</li>
        <li><strong>Embeddings:</strong> Google Vertex AI text-embedding-005</li>
        <li><strong>Search:</strong> Vector similarity using cosine distance</li>
    </ul>
    
    <h2>Supported Formats</h2>
    
    <table border="1">
        <thead>
            <tr>
                <th>Category</th>
                <th>Formats</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Documents</td>
                <td>PDF, TXT, MD, HTML</td>
            </tr>
            <tr>
                <td>Structured Data</td>
                <td>JSON, XML, YAML</td>
            </tr>
        </tbody>
    </table>
    
    <p>For more info, visit <a href="https://github.com/RostislavDublin/rag-lab">RAG Lab Repository</a>.</p>
</body>
</html>"""
    
    text = processor.extract_text(html_content, '.html')
    
    # Check Markdown conversion preserved structure
    assert 'RAG System Overview' in text  # H1 heading
    assert 'Retrieval-Augmented Generation' in text  # Content
    assert 'Key Components' in text  # H2 heading
    assert 'PostgreSQL' in text  # List items
    assert 'pgvector' in text
    assert 'Supported Formats' in text  # Table heading
    assert 'Documents' in text  # Table content
    assert 'Structured Data' in text
    
    # Verify HTML tags removed (converted to Markdown)
    assert '<html>' not in text
    assert '<table>' not in text
    assert '<strong>' not in text
    assert '<li>' not in text
    
    # Verify links preserved (converted to Markdown)
    assert 'rag-lab' in text or 'RAG Lab Repository' in text
    
    print(f"\n=== Extracted HTML ({len(text)} chars) ===")
    print(text[:500])
