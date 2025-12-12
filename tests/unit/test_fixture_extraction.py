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


def test_json_fixture_extraction(processor, fixtures_dir):
    """Test extraction from sample_data.json fixture"""
    json_file = fixtures_dir / "sample_data.json"
    
    with open(json_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.json')
    
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


def test_xml_fixture_extraction(processor, fixtures_dir):
    """Test extraction from sample_documentation.xml fixture"""
    xml_file = fixtures_dir / "sample_documentation.xml"
    
    with open(xml_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.xml')
    
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
    
    formats = {
        'json': 'sample_data.json',
        'xml': 'sample_documentation.xml',
        'md': 'vector_databases.md',
        'csv': 'products.csv',
        'yaml': 'config.yaml',
        'log': 'rag_system_operations.log',
    }
    
    for fmt, filename in formats.items():
        file_path = fixtures_dir / filename
        
        with open(file_path, 'rb') as f:
            content = f.read()
        
        text = processor.extract_text(content, f'.{fmt}')
        
        # All should produce substantial text
        assert len(text) > 100, f"{fmt} produced too little text"
        
        # Should be mostly readable (not binary garbage)
        assert text.isprintable() or '\n' in text, f"{fmt} produced non-printable text"
        
        print(f"{fmt.upper()}: {len(text)} chars extracted")


def test_csv_fixture_extraction(processor, fixtures_dir):
    """Test extraction from products.csv fixture"""
    csv_file = fixtures_dir / "products.csv"
    
    with open(csv_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.csv')
    
    # Check CSV content preserved
    assert 'product,price,stock,category' in text  # Header
    assert 'Laptop' in text
    assert '999' in text
    assert 'Electronics' in text
    
    # CSV kept as plain text (good for RAG - readable structure)
    print(f"\n=== Extracted CSV ({len(text)} chars) ===")
    print(text[:200])


def test_yaml_fixture_extraction(processor, fixtures_dir):
    """Test extraction from config.yaml fixture"""
    yaml_file = fixtures_dir / "config.yaml"
    
    with open(yaml_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.yaml')
    
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


def test_html_fixture_extraction(processor, fixtures_dir):
    """Test extraction from sample.html fixture"""
    html_file = fixtures_dir / "sample.html"
    
    with open(html_file, 'rb') as f:
        content = f.read()
    
    text = processor.extract_text(content, '.html')
    
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
