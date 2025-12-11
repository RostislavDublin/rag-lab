"""Test chunking algorithm without Vertex AI calls"""

from src.document_processor import DocumentProcessor


def test_bug_too_many_chunking():
    """Test that bug_too_many.txt produces reasonable number of chunks"""
    processor = DocumentProcessor(chunk_size=500, chunk_overlap=50)
    
    # Read the problematic file
    with open("tests/fixtures/documents/bug_too_many.txt", "r") as f:
        text = f.read()
    
    print(f"File size: {len(text)} characters")
    
    # Chunk without embeddings
    chunks = processor.chunk_text(text)
    
    print(f"Number of chunks: {len(chunks)}")
    print(f"First chunk preview: {chunks[0][0][:100]}...")
    print(f"Last chunk preview: {chunks[-1][0][:100]}...")
    
    # Should be around 59 chunks (26598 / 450)
    assert len(chunks) < 100, f"Too many chunks: {len(chunks)}"
    assert len(chunks) > 0, "No chunks generated"
