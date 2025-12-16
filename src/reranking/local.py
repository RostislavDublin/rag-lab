"""
Local cross-encoder reranker using sentence-transformers.

Supports any HuggingFace cross-encoder model.
Model loads once and stays in memory for fast inference.
"""

from typing import List
import logging
import numpy as np

from .base import BaseReranker, RerankResult

logger = logging.getLogger(__name__)


class LocalCrossEncoderReranker(BaseReranker):
    """
    Local cross-encoder reranker using sentence-transformers.
    
    Supports any HuggingFace cross-encoder model.
    Model loads once and stays in memory for fast inference.
    """
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
        """
        Initialize local cross-encoder.
        
        Args:
            model_name: HuggingFace model identifier
                - 'cross-encoder/ms-marco-MiniLM-L-12-v2' (120MB, fast)
                - 'BAAI/bge-reranker-base' (1.1GB, better quality)
                - 'BAAI/bge-reranker-large' (1.4GB, best quality)
        """
        self.model_name = model_name
        self.model = None  # Lazy loading
        logger.info(f"LocalCrossEncoderReranker initialized (model will load on first use): {model_name}")
    
    def _ensure_loaded(self):
        """Lazy load model on first use (avoid startup overhead)"""
        if self.model is None:
            logger.info(f"Loading cross-encoder model: {self.model_name}")
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name)
                logger.info(f"Model loaded successfully: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to load model {self.model_name}: {e}")
                raise
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[RerankResult]:
        """Rerank documents using cross-encoder model."""
        self._ensure_loaded()
        
        if not documents:
            return []
        
        # Create query-document pairs
        pairs = [(query, doc) for doc in documents]
        
        # Score all pairs (batch inference)
        scores = self.model.predict(pairs, show_progress_bar=False)
        
        # Convert to numpy for sorting
        scores = np.array(scores)
        
        # Get top-k indices (argsort descending)
        top_k = min(top_k, len(documents))
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        # Build results
        results = [
            RerankResult(
                index=int(idx),
                score=float(scores[idx]),
                text=documents[idx]
            )
            for idx in top_indices
        ]
        
        logger.info(f"Reranked {len(documents)} documents, returning top {top_k}")
        return results
    
    def get_model_info(self) -> dict:
        """Get model metadata."""
        return {
            "name": self.model_name,
            "type": "local_cross_encoder",
            "provider": "sentence-transformers",
            "loaded": self.model is not None
        }
    
    def close(self):
        """Free model memory."""
        if self.model is not None:
            logger.info(f"Closing model: {self.model_name}")
            del self.model
            self.model = None
