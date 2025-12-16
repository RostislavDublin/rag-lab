"""
Integration tests for reranking module

These tests use real models and verify actual inference behavior.
First run will download ~23MB TinyBERT model to ~/.cache/huggingface/
Model is loaded ONCE per test session and reused across all tests.
"""

import pytest
from src.reranking import LocalCrossEncoderReranker, get_reranker


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def shared_reranker():
    """
    Create a single reranker instance for all tests.
    
    Model is loaded once at the start of the test session and reused.
    This avoids reloading the same 23MB model 5 times.
    """
    reranker = LocalCrossEncoderReranker("cross-encoder/ms-marco-TinyBERT-L-2-v2")
    yield reranker
    # Cleanup after all tests
    reranker.close()


class TestLocalCrossEncoderIntegration:
    """Integration tests with real cross-encoder model"""
    
    def test_real_model_loading(self, shared_reranker):
        """Test loading real cross-encoder model from HuggingFace"""
        # Force load if not loaded yet
        shared_reranker._ensure_loaded()
        
        # Model should be loaded now
        assert shared_reranker.model is not None
        
        # Check model info
        info = shared_reranker.get_model_info()
        assert info["loaded"] is True
        assert info["name"] == "cross-encoder/ms-marco-TinyBERT-L-2-v2"
        assert info["type"] == "local_cross_encoder"
        assert info["provider"] == "sentence-transformers"
    
    def test_real_reranking(self, shared_reranker):
        """Test reranking with real model inference"""
        query = "What is Python?"
        documents = [
            "Python is a high-level programming language.",
            "Java is used for enterprise applications.",
            "Python was created by Guido van Rossum.",
            "JavaScript is a web programming language.",
            "Python is popular for data science and ML.",
        ]
        
        results = shared_reranker.rerank(query, documents, top_k=3)
        
        # Verify results structure
        assert len(results) == 3
        assert all(hasattr(r, 'index') for r in results)
        assert all(hasattr(r, 'score') for r in results)
        assert all(hasattr(r, 'text') for r in results)
        
        # Verify scores are in descending order
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        
        # Verify Python-related docs ranked higher
        top_texts = [r.text for r in results]
        python_docs = [d for d in documents if "Python" in d]
        
        # At least 2 of top 3 should be Python-related
        python_in_top = sum(1 for text in top_texts if text in python_docs)
        assert python_in_top >= 2, f"Expected Python docs in top results, got: {top_texts}"
    
    def test_reranking_improves_relevance(self, shared_reranker):
        """Test that reranking improves document ordering"""
        query = "machine learning frameworks for computer vision"
        
        # Simulate pre-ranked documents (as if from vector search)
        # Intentionally put less relevant doc first
        documents = [
            "TensorFlow is used for web development.",  # Less relevant (wrong context)
            "PyTorch and TensorFlow are ML frameworks.",  # Most relevant
            "OpenCV is a computer vision library.",  # Relevant
            "Python is a programming language.",  # Generic, less relevant
            "PyTorch excels at computer vision tasks.",  # Very relevant
        ]
        
        results = shared_reranker.rerank(query, documents, top_k=3)
        
        # Top result should be about ML frameworks + CV
        top_result = results[0]
        assert "PyTorch" in top_result.text or "TensorFlow" in top_result.text
        assert "vision" in top_result.text or "ML" in top_result.text
        
        # Should not have generic Python doc in top 3
        top_texts = [r.text for r in results]
        assert "Python is a programming language." not in top_texts
    
    def test_factory_integration(self, monkeypatch):
        """Test factory creates working reranker from env vars"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        monkeypatch.setenv("RERANKER_MODEL", "cross-encoder/ms-marco-TinyBERT-L-2-v2")
        
        # Force reload to pick up new env vars
        reranker = get_reranker(force_reload=True)
        
        assert reranker is not None
        assert isinstance(reranker, LocalCrossEncoderReranker)
        
        # Test it works
        results = reranker.rerank(
            query="test query",
            documents=["doc1", "doc2"],
            top_k=1
        )
        
        assert len(results) == 1
        assert results[0].text in ["doc1", "doc2"]
        
        # Cleanup
        from src.reranking.factory import RerankingFactory
        RerankingFactory.cleanup()
    
    def test_empty_and_edge_cases(self, shared_reranker):
        """Test edge cases with real model"""
        # Empty documents
        results = shared_reranker.rerank("query", [], top_k=5)
        assert results == []
        
        # Single document
        results = shared_reranker.rerank("query", ["single doc"], top_k=5)
        assert len(results) == 1
        assert results[0].text == "single doc"
        
        # top_k larger than documents
        results = shared_reranker.rerank("query", ["doc1", "doc2"], top_k=10)
        assert len(results) == 2
