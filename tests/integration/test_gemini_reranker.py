"""
Integration tests for Gemini LLM reranker.

Tests actual Gemini API calls with real credentials.
"""

import pytest
import os


@pytest.mark.integration
def test_gemini_reranker_initialization():
    """Test Gemini reranker can be initialized with proper credentials."""
    from src.reranking import GeminiReranker
    
    # Check required env vars
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    assert project_id, "GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID env var required"
    
    # Initialize reranker
    reranker = GeminiReranker(
        model_name="gemini-2.0-flash-exp",
        project_id=project_id,
        location="us-central1"
    )
    
    # Verify initialization
    info = reranker.get_model_info()
    assert info["name"] == "gemini-2.0-flash-exp"
    assert info["type"] == "gemini-llm"
    assert info["project"] == project_id
    assert info["location"] == "us-central1"
    assert info["temperature"] == 0.0
    
    print(f"✓ Gemini reranker initialized: {info}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gemini_reranker_simple_reranking():
    """Test Gemini reranker with simple documents."""
    from src.reranking import GeminiReranker
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    reranker = GeminiReranker(
        model_name="gemini-2.0-flash-exp",
        project_id=project_id,
        location="us-central1"
    )
    
    # Test query and documents
    query = "What is the capital of France?"
    documents = [
        "Paris is the capital and largest city of France.",  # RELEVANT
        "Python is a programming language.",  # IRRELEVANT
        "The Eiffel Tower is located in Paris, France.",  # SOMEWHAT RELEVANT
    ]
    
    # Rerank
    results = await reranker.rerank(query, documents, top_k=3)
    
    # Verify results
    assert len(results) == 3
    
    # First result should be most relevant
    assert results[0].index == 0  # "Paris is the capital..."
    assert results[0].score > 0.7  # High relevance
    
    # Last result should be least relevant
    assert results[2].index == 1  # "Python is..."
    assert results[2].score < 0.3  # Low relevance
    
    print(f"\n✓ Reranking results:")
    for i, result in enumerate(results):
        doc_preview = documents[result.index][:50]
        print(f"  {i+1}. score={result.score:.3f}, doc={doc_preview}...")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gemini_reranker_keyword_ambiguity():
    """Test Gemini resolves keyword ambiguity better than vector search."""
    from src.reranking import GeminiReranker
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    reranker = GeminiReranker(
        model_name="gemini-2.0-flash-exp",
        project_id=project_id,
        location="us-central1"
    )
    
    # Query with ambiguous keyword "score"
    query = "What are the compliance assessment scores?"
    documents = [
        "Customer satisfaction scores improved by 15% this quarter.",  # WRONG - business metrics
        "GDPR compliance assessment: Overall score 8.5/10. Critical findings require immediate action.",  # CORRECT
        "Financial performance scores show strong revenue growth.",  # WRONG - financials
    ]
    
    # Rerank
    results = await reranker.rerank(query, documents, top_k=3)
    
    # First result should be GDPR compliance (index 1)
    assert results[0].index == 1, f"Expected GDPR doc (index 1), got index {results[0].index}"
    assert results[0].score > 0.7, f"Expected high score for GDPR doc, got {results[0].score}"
    
    print(f"\n✓ Keyword ambiguity resolved:")
    for i, result in enumerate(results):
        doc_preview = documents[result.index][:60]
        print(f"  {i+1}. score={result.score:.3f}, doc={doc_preview}...")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gemini_reranker_via_factory():
    """Test Gemini reranker creation via factory."""
    import os
    
    # Set env vars
    os.environ["RERANKER_ENABLED"] = "true"
    os.environ["RERANKER_TYPE"] = "gemini"
    os.environ["RERANKER_MODEL"] = "gemini-2.0-flash-exp"
    
    # Ensure GOOGLE_CLOUD_PROJECT is set
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    
    from src.reranking.factory import RerankingFactory
    
    # Force reload to pick up new env vars
    reranker = RerankingFactory.create(force_reload=True)
    
    assert reranker is not None
    info = reranker.get_model_info()
    assert info["type"] == "gemini-llm"
    
    # Test reranking works
    results = await reranker.rerank(
        query="test query",
        documents=["doc1", "doc2"],
        top_k=2
    )
    assert len(results) == 2
    
    print(f"✓ Factory created Gemini reranker: {info['name']}")


@pytest.mark.integration  
@pytest.mark.asyncio
async def test_gemini_reranker_truncation():
    """Test Gemini handles long documents via truncation."""
    from src.reranking import GeminiReranker
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    reranker = GeminiReranker(
        model_name="gemini-2.0-flash-exp",
        project_id=project_id,
        location="us-central1"
    )
    
    # Very long document (>2000 chars)
    long_doc = "This is a test document. " * 200  # ~5000 chars
    query = "test document"
    
    # Should not raise error (truncation handled)
    results = await reranker.rerank(query, [long_doc], top_k=1)
    assert len(results) == 1
    assert results[0].score > 0.5  # Should still match "test document"
    
    print(f"✓ Long document handled (truncated to 2000 chars)")
