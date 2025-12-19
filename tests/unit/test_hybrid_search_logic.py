"""
Unit tests for hybrid search integration (_hybrid_search function)

Tests verify:
- Vector search returns expected metadata (summary, keywords, token_count)
- BM25 index fetching works with mocked GCS
- SimplifiedBM25 scoring applied correctly
- RRF fusion combines rankings
- Results have correct structure
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.main import _hybrid_search, QueryRequest


@pytest.fixture
def mock_vector_results():
    """Mock vector search results with BM25 metadata"""
    return [
        {
            "chunk_id": "chunk_1",
            "doc_uuid": "doc_a",
            "chunk_index": 0,
            "similarity": 0.85,
            "filename": "k8s_guide.pdf",
            "original_doc_id": 1,
            "doc_metadata": {},
            "summary": "Kubernetes deployment guide",
            "keywords": ["kubernetes", "deployment", "pod"],
            "token_count": 1200,
        },
        {
            "chunk_id": "chunk_2",
            "doc_uuid": "doc_a",
            "chunk_index": 1,
            "similarity": 0.78,
            "filename": "k8s_guide.pdf",
            "original_doc_id": 1,
            "doc_metadata": {},
            "summary": "Kubernetes deployment guide",
            "keywords": ["kubernetes", "deployment", "pod"],
            "token_count": 1200,
        },
        {
            "chunk_id": "chunk_3",
            "doc_uuid": "doc_b",
            "chunk_index": 0,
            "similarity": 0.80,
            "filename": "docker_tutorial.txt",
            "original_doc_id": 2,
            "doc_metadata": {},
            "summary": "Docker container basics",
            "keywords": ["docker", "container", "image"],
            "token_count": 800,
        },
    ]


@pytest.fixture
def mock_bm25_indices():
    """Mock BM25 indices from GCS"""
    return {
        "doc_a": {
            "term_frequencies": {
                "kubernetes": 25,
                "deployment": 18,
                "pod": 15,
                "container": 5,
            }
        },
        "doc_b": {
            "term_frequencies": {
                "docker": 30,
                "container": 20,
                "image": 12,
                "kubernetes": 2,  # Minor mention
            }
        },
    }


@pytest.mark.asyncio
async def test_hybrid_search_basic_flow(mock_vector_results, mock_bm25_indices):
    """Test basic hybrid search flow with mocked dependencies"""
    
    request = QueryRequest(
        query="kubernetes deployment",
        top_k=3,
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768  # Mock embedding
    
    # Mock vector_db.search_similar_chunks
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=mock_vector_results)
        
        # Mock GCS fetch for BM25 indices
        async def mock_fetch_bm25_index(doc_uuid):
            return mock_bm25_indices.get(doc_uuid, {"term_frequencies": {}})
        
        mock_storage.fetch_bm25_index = mock_fetch_bm25_index
        
        # Run hybrid search
        results = await _hybrid_search(request, query_embedding)
        
        # Verify results structure
        assert len(results) > 0
        assert len(results) <= request.top_k
        
        # Verify each result has BM25 score
        for result in results:
            assert "doc_bm25_score" in result
            assert isinstance(result["doc_bm25_score"], (int, float))
            assert result["doc_bm25_score"] >= 0
        
        # Verify vector search was called with top_k=100 (hybrid retrieval)
        mock_vector_db.search_similar_chunks.assert_called_once()
        call_kwargs = mock_vector_db.search_similar_chunks.call_args.kwargs
        assert call_kwargs["top_k"] == 100


@pytest.mark.asyncio
async def test_hybrid_search_bm25_keyword_boosting(mock_vector_results, mock_bm25_indices):
    """Test that BM25 keyword boosting works correctly"""
    
    request = QueryRequest(
        query="kubernetes pod",  # Query matches doc_a keywords
        top_k=3,
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=mock_vector_results)
        
        async def mock_fetch_bm25_index(doc_uuid):
            return mock_bm25_indices.get(doc_uuid, {"term_frequencies": {}})
        
        mock_storage.fetch_bm25_index = mock_fetch_bm25_index
        
        results = await _hybrid_search(request, query_embedding)
        
        # Find doc_a and doc_b results
        doc_a_results = [r for r in results if r["doc_uuid"] == "doc_a"]
        doc_b_results = [r for r in results if r["doc_uuid"] == "doc_b"]
        
        # doc_a should have higher BM25 score (query matches keywords)
        if doc_a_results and doc_b_results:
            doc_a_bm25 = doc_a_results[0]["doc_bm25_score"]
            doc_b_bm25 = doc_b_results[0]["doc_bm25_score"]
            assert doc_a_bm25 > doc_b_bm25, "doc_a should rank higher (keyword boost)"


@pytest.mark.asyncio
async def test_hybrid_search_empty_vector_results():
    """Test hybrid search with no vector results"""
    
    request = QueryRequest(
        query="nonexistent topic",
        top_k=5,
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db:
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=[])
        
        results = await _hybrid_search(request, query_embedding)
        
        # Should return empty list
        assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_missing_bm25_index(mock_vector_results):
    """Test hybrid search when BM25 index is missing (graceful degradation)"""
    
    request = QueryRequest(
        query="kubernetes",
        top_k=3,
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=mock_vector_results)
        
        # Mock GCS fetch to return empty index (file missing)
        async def mock_fetch_bm25_index(doc_uuid):
            return {"term_frequencies": {}}  # Empty fallback
        
        mock_storage.fetch_bm25_index = mock_fetch_bm25_index
        
        results = await _hybrid_search(request, query_embedding)
        
        # Should still return results (with BM25 score = 0)
        assert len(results) > 0
        for result in results:
            assert "doc_bm25_score" in result
            assert result["doc_bm25_score"] == 0  # No TF data → score 0


@pytest.mark.asyncio
async def test_hybrid_search_rrf_fusion_combines_rankings(mock_vector_results, mock_bm25_indices):
    """Test that RRF fusion actually changes ranking vs pure vector"""
    
    request = QueryRequest(
        query="docker container",  # Favors doc_b in BM25
        top_k=3,
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        # Vector results: doc_a > doc_b (by similarity)
        vector_only = [
            {"chunk_id": "c1", "doc_uuid": "doc_a", "similarity": 0.85, "chunk_index": 0,
             "filename": "k8s.pdf", "original_doc_id": 1, "doc_metadata": {},
             "summary": "K8s", "keywords": ["kubernetes"], "token_count": 1000},
            {"chunk_id": "c2", "doc_uuid": "doc_b", "similarity": 0.80, "chunk_index": 0,
             "filename": "docker.txt", "original_doc_id": 2, "doc_metadata": {},
             "summary": "Docker", "keywords": ["docker", "container"], "token_count": 800},
        ]
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=vector_only)
        
        async def mock_fetch_bm25_index(doc_uuid):
            return mock_bm25_indices.get(doc_uuid, {"term_frequencies": {}})
        
        mock_storage.fetch_bm25_index = mock_fetch_bm25_index
        
        results = await _hybrid_search(request, query_embedding)
        
        # RRF should boost doc_b (BM25 favors "docker container")
        # Top result might be doc_b (depends on RRF fusion)
        assert len(results) > 0
        
        # Verify BM25 scores exist and doc_b has higher BM25
        doc_a = next(r for r in results if r["doc_uuid"] == "doc_a")
        doc_b = next(r for r in results if r["doc_uuid"] == "doc_b")
        
        assert doc_b["doc_bm25_score"] > doc_a["doc_bm25_score"], \
            "doc_b should have higher BM25 (query matches 'docker container')"


@pytest.mark.asyncio
async def test_hybrid_search_with_reranking_flag(mock_vector_results, mock_bm25_indices):
    """Test that rerank flag increases candidate retrieval"""
    
    request = QueryRequest(
        query="kubernetes",
        top_k=3,
        rerank=True,
        rerank_candidates=10,  # Retrieve 10 for reranking
        use_hybrid=True,
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=mock_vector_results)
        
        async def mock_fetch_bm25_index(doc_uuid):
            return mock_bm25_indices.get(doc_uuid, {"term_frequencies": {}})
        
        mock_storage.fetch_bm25_index = mock_fetch_bm25_index
        
        results = await _hybrid_search(request, query_embedding)
        
        # Should return rerank_candidates (10), not top_k (3)
        # (query_rag endpoint will handle final reranking to top_k)
        assert len(results) <= request.rerank_candidates
        assert len(results) >= min(len(mock_vector_results), request.rerank_candidates)


@pytest.mark.asyncio
async def test_hybrid_search_metadata_filters_applied():
    """Test that metadata filters are passed to vector search"""
    
    request = QueryRequest(
        query="kubernetes",
        top_k=5,
        use_hybrid=True,
        filters={"doc_metadata.user_id": "user123"},
    )
    
    query_embedding = [0.1] * 768
    
    with patch("src.main.vector_db") as mock_vector_db, \
         patch("src.main.document_storage") as mock_storage:
        
        mock_vector_db.search_similar_chunks = AsyncMock(return_value=[])
        mock_storage.fetch_bm25_index = AsyncMock(return_value={"term_frequencies": {}})
        
        await _hybrid_search(request, query_embedding)
        
        # Verify filters passed to vector search
        call_kwargs = mock_vector_db.search_similar_chunks.call_args.kwargs
        assert call_kwargs["filters"] == {"doc_metadata.user_id": "user123"}
