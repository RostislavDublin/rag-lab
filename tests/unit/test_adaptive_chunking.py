"""
Unit tests for adaptive chunking with retry logic
"""
import pytest
from src.document_processor import DocumentProcessor, EmbeddingProvider


def test_aggressive_chunk_size():
    """Test that default chunk size is balanced for RAG quality (2000)"""
    # Use Vertex AI provider (default) - doesn't require sentence_transformers
    processor = DocumentProcessor()
    
    assert processor.chunk_size == 2000
    assert processor.chunk_overlap == 200


def test_chunking_with_large_chunks():
    """Test that large chunks are created correctly"""
    processor = DocumentProcessor()
    
    # Create text that would be ~20 chunks with old size (500), ~5 with new size (2000)
    text = "This is a sentence. " * 500  # 10,000 chars
    
    chunks = processor.chunk_text(text)
    
    # Should create fewer, larger chunks (~5 chunks)
    assert len(chunks) <= 6, f"Expected <=6 chunks, got {len(chunks)}"
    
    # First chunk should be close to 2000 chars
    first_chunk_size = len(chunks[0][0])
    assert first_chunk_size >= 1800, f"First chunk too small: {first_chunk_size} chars"
    assert first_chunk_size <= 2200, f"First chunk too large: {first_chunk_size} chars"


def test_chunk_metadata_still_correct():
    """Ensure chunk metadata is preserved with new size"""
    processor = DocumentProcessor()
    
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = processor.chunk_text(text)
    
    # Check metadata structure
    assert isinstance(chunks, list)
    assert all(isinstance(chunk, tuple) for chunk in chunks)
    assert all(len(chunk) == 2 for chunk in chunks)
    
    # Check metadata fields
    chunk_text, metadata = chunks[0]
    assert "chunk_index" in metadata
    assert "start_char" in metadata
    assert "end_char" in metadata


def test_large_file_chunking():
    """Test chunking with the problematic bug_too_many.txt file"""
    processor = DocumentProcessor()
    
    # Load the fixture
    with open("tests/fixtures/documents/bug_too_many.txt", "r") as f:
        text = f.read()
    
    chunks = processor.chunk_text(text)
    
    # With 2000 char chunks, should be ~13-15 chunks (was 58 with 500 chars)
    assert len(chunks) <= 20, f"Too many chunks: {len(chunks)} (expected ~13-15)"
    assert len(chunks) >= 10, f"Too few chunks: {len(chunks)} (expected ~13-15)"
    
    print(f"\nChunking results for bug_too_many.txt:")
    print(f"  File size: {len(text)} chars")
    print(f"  Chunks created: {len(chunks)}")
    print(f"  Avg chunk size: {len(text) // len(chunks)} chars")
    
    # Verify no empty chunks
    assert all(len(chunk[0]) > 0 for chunk in chunks), "Found empty chunk"
