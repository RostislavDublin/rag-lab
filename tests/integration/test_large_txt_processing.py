"""Integration test for large TXT file processing"""

import pytest
from pathlib import Path

from src.document_processor import DocumentProcessor, EmbeddingProvider


@pytest.fixture
def doc_processor():
    """DocumentProcessor with small chunk size for testing"""
    return DocumentProcessor(
        embedding_provider=EmbeddingProvider.VERTEX_AI,
        chunk_size=500,
        chunk_overlap=50
    )


def test_large_txt_extraction(doc_processor):
    """Test that large TXT file can be extracted"""
    txt_path = Path(__file__).parent.parent / "fixtures" / "documents" / "bug_too_many.txt"
    
    with open(txt_path, "rb") as f:
        content = f.read()
    
    # This should not hang or crash
    text = doc_processor.extract_text(content, "txt")
    
    assert text is not None
    assert len(text) > 0
    print(f"Extracted {len(text)} characters")


def test_large_txt_chunking(doc_processor):
    """Test that large TXT file chunking is reasonable"""
    txt_path = Path(__file__).parent.parent / "fixtures" / "documents" / "bug_too_many.txt"
    
    with open(txt_path, "rb") as f:
        content = f.read()
    
    text = doc_processor.extract_text(content, "txt")
    chunks = doc_processor.chunk_text(text)
    
    print(f"Generated {len(chunks)} chunks")
    
    # PROBLEM: 26KB one-liner creates hundreds of chunks
    # This will cause timeout when processing embeddings
    assert len(chunks) > 0
    assert len(chunks) < 1000, f"Too many chunks: {len(chunks)}. Will timeout on embeddings!"


@pytest.mark.asyncio
async def test_large_txt_processing_timeout(doc_processor):
    """Test that processing doesn't hang indefinitely"""
    import asyncio
    
    txt_path = Path(__file__).parent.parent / "fixtures" / "documents" / "bug_too_many.txt"
    
    with open(txt_path, "rb") as f:
        content = f.read()
    
    # Should complete or timeout within 60 seconds
    try:
        result = await asyncio.wait_for(
            doc_processor.process_document(content, "bug_too_many.txt", "txt"),
            timeout=60.0
        )
        print(f"Processing completed: {len(result)} chunks with embeddings")
    except asyncio.TimeoutError:
        pytest.fail("Processing timed out after 60 seconds - this is the bug!")
