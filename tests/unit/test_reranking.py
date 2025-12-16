"""
Unit tests for reranking module

All tests use mocks to avoid loading real models or making API calls.
Tests are marked with @pytest.mark.unit for explicit categorization.
"""

import pytest
from unittest.mock import Mock, patch

pytestmark = pytest.mark.unit
from src.reranking import (
    BaseReranker,
    RerankResult,
    LocalCrossEncoderReranker,
    CohereReranker,
    get_reranker,
)
from src.reranking.factory import RerankingFactory

# Check if cohere is available
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False


class TestRerankResult:
    """Test RerankResult dataclass"""
    
    def test_rerank_result_creation(self):
        """Test creating RerankResult"""
        result = RerankResult(
            index=0,
            score=0.95,
            text="test document"
        )
        assert result.index == 0
        assert result.score == 0.95
        assert result.text == "test document"


class TestLocalCrossEncoderReranker:
    """Test local cross-encoder reranker"""
    
    def test_initialization(self):
        """Test reranker initialization (lazy loading)"""
        reranker = LocalCrossEncoderReranker("cross-encoder/ms-marco-MiniLM-L-12-v2")
        assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-12-v2"
        assert reranker.model is None  # Not loaded yet
    
    def test_get_model_info_before_load(self):
        """Test model info before loading"""
        reranker = LocalCrossEncoderReranker()
        info = reranker.get_model_info()
        assert info["type"] == "local_cross_encoder"
        assert info["provider"] == "sentence-transformers"
        assert info["loaded"] is False
    
    @patch('sentence_transformers.CrossEncoder')
    def test_rerank(self, mock_cross_encoder_class):
        """Test reranking with mocked model"""
        # Mock model
        mock_model = Mock()
        mock_model.predict.return_value = [0.9, 0.7, 0.85]  # Scores for 3 docs
        mock_cross_encoder_class.return_value = mock_model
        
        # Create reranker and rerank
        reranker = LocalCrossEncoderReranker()
        results = reranker.rerank(
            query="test query",
            documents=["doc1", "doc2", "doc3"],
            top_k=2
        )
        
        # Verify
        assert len(results) == 2
        assert results[0].index == 0  # doc1 has highest score (0.9)
        assert results[0].score == 0.9
        assert results[0].text == "doc1"
        assert results[1].index == 2  # doc3 has second highest (0.85)
        assert results[1].score == 0.85
        
        # Verify model was called
        mock_model.predict.assert_called_once()
    
    @patch('sentence_transformers.CrossEncoder')
    def test_rerank_empty_documents(self, mock_cross_encoder_class):
        """Test reranking with empty document list"""
        reranker = LocalCrossEncoderReranker()
        results = reranker.rerank("query", [], top_k=5)
        assert results == []
    
    @patch('sentence_transformers.CrossEncoder')
    def test_close(self, mock_cross_encoder_class):
        """Test cleanup"""
        mock_model = Mock()
        mock_cross_encoder_class.return_value = mock_model
        
        reranker = LocalCrossEncoderReranker()
        reranker._ensure_loaded()  # Load model
        assert reranker.model is not None
        
        reranker.close()
        assert reranker.model is None


class TestCohereReranker:
    """Test Cohere API reranker"""
    
    def test_initialization_no_api_key(self, monkeypatch):
        """Test initialization fails without API key"""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        
        with pytest.raises(ValueError, match="COHERE_API_KEY"):
            CohereReranker()
    
    @pytest.mark.skipif(not COHERE_AVAILABLE, reason="cohere package not installed")
    @patch('cohere.Client')
    def test_initialization_with_api_key(self, mock_cohere_client, monkeypatch):
        """Test successful initialization with API key"""
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        
        mock_client = Mock()
        mock_cohere_client.return_value = mock_client
        
        reranker = CohereReranker()
        assert reranker.model == "rerank-english-v3.0"
        assert reranker.client == mock_client
        mock_cohere_client.assert_called_once_with("test-key")
    
    @pytest.mark.skipif(not COHERE_AVAILABLE, reason="cohere package not installed")
    @patch('cohere.Client')
    def test_rerank(self, mock_cohere_client, monkeypatch):
        """Test Cohere reranking"""
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        
        # Mock Cohere response
        mock_result1 = Mock()
        mock_result1.index = 2
        mock_result1.relevance_score = 0.95
        
        mock_result2 = Mock()
        mock_result2.index = 0
        mock_result2.relevance_score = 0.88
        
        mock_response = Mock()
        mock_response.results = [mock_result1, mock_result2]
        
        mock_client = Mock()
        mock_client.rerank.return_value = mock_response
        mock_cohere_client.return_value = mock_client
        
        # Test
        reranker = CohereReranker()
        results = reranker.rerank(
            query="test query",
            documents=["doc1", "doc2", "doc3"],
            top_k=2
        )
        
        # Verify
        assert len(results) == 2
        assert results[0].index == 2
        assert results[0].score == 0.95
        assert results[0].text == "doc3"
        assert results[1].index == 0
        assert results[1].score == 0.88
        assert results[1].text == "doc1"
        
        mock_client.rerank.assert_called_once()
    
    @pytest.mark.skipif(not COHERE_AVAILABLE, reason="cohere package not installed")
    @patch('cohere.Client')
    def test_get_model_info(self, mock_cohere_client, monkeypatch):
        """Test model info"""
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        mock_cohere_client.return_value = Mock()
        
        reranker = CohereReranker("rerank-multilingual-v3.0")
        info = reranker.get_model_info()
        assert info["name"] == "rerank-multilingual-v3.0"
        assert info["type"] == "api"
        assert info["provider"] == "cohere"


class TestRerankingFactory:
    """Test reranking factory"""
    
    def setup_method(self):
        """Reset factory singleton before each test"""
        RerankingFactory._instance = None
    
    def teardown_method(self):
        """Cleanup after each test"""
        RerankingFactory.cleanup()
    
    def test_disabled_by_default(self, monkeypatch):
        """Test reranking disabled by default"""
        monkeypatch.setenv("RERANKER_ENABLED", "false")
        
        reranker = get_reranker()
        assert reranker is None
    
    @patch('sentence_transformers.CrossEncoder')
    def test_local_reranker(self, mock_cross_encoder, monkeypatch):
        """Test creating local reranker"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        monkeypatch.setenv("RERANKER_MODEL", "test-model")
        
        reranker = get_reranker()
        assert isinstance(reranker, LocalCrossEncoderReranker)
        assert reranker.model_name == "test-model"
    
    @patch('sentence_transformers.CrossEncoder')
    def test_local_reranker_default_model(self, mock_cross_encoder, monkeypatch):
        """Test local reranker with default model"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        monkeypatch.setenv("RERANKER_MODEL", "")
        
        reranker = get_reranker()
        assert isinstance(reranker, LocalCrossEncoderReranker)
        assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-12-v2"
    
    @pytest.mark.skipif(not COHERE_AVAILABLE, reason="cohere package not installed")
    @patch('cohere.Client')
    def test_cohere_reranker(self, mock_cohere_client, monkeypatch):
        """Test creating Cohere reranker"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "cohere")
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        monkeypatch.setenv("RERANKER_MODEL", "rerank-multilingual-v3.0")
        
        mock_cohere_client.return_value = Mock()
        
        reranker = get_reranker()
        assert isinstance(reranker, CohereReranker)
        assert reranker.model == "rerank-multilingual-v3.0"
    
    def test_singleton_caching(self, monkeypatch):
        """Test factory caches instance"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        
        with patch('sentence_transformers.CrossEncoder'):
            reranker1 = get_reranker()
            reranker2 = get_reranker()
            assert reranker1 is reranker2  # Same instance
    
    def test_force_reload(self, monkeypatch):
        """Test force reload creates new instance"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        
        with patch('sentence_transformers.CrossEncoder'):
            reranker1 = get_reranker()
            reranker2 = get_reranker(force_reload=True)
            assert reranker1 is not reranker2  # Different instances
    
    def test_unknown_reranker_type(self, monkeypatch):
        """Test error with unknown reranker type"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "invalid")
        
        with pytest.raises(ValueError, match="Unknown reranker type"):
            get_reranker()
    
    def test_cleanup(self, monkeypatch):
        """Test cleanup releases resources"""
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_TYPE", "local")
        
        with patch('sentence_transformers.CrossEncoder'):
            reranker = get_reranker()
            assert RerankingFactory._instance is not None
            
            RerankingFactory.cleanup()
            assert RerankingFactory._instance is None
