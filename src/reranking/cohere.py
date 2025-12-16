"""
Cohere Rerank API implementation.

Requires COHERE_API_KEY environment variable.
Pricing: ~$2 per 1000 searches (with 50 documents each)
"""

from typing import List
import os
import logging

from .base import BaseReranker, RerankResult

logger = logging.getLogger(__name__)


class CohereReranker(BaseReranker):
    """
    Cohere Rerank API implementation.
    
    Requires COHERE_API_KEY environment variable.
    Pricing: ~$2 per 1000 searches (with 50 documents each)
    """
    
    def __init__(self, model: str = "rerank-english-v3.0"):
        """
        Initialize Cohere reranker.
        
        Args:
            model: Cohere rerank model
                - 'rerank-english-v3.0' (latest, best)
                - 'rerank-multilingual-v3.0' (100+ languages)
        """
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY environment variable required for Cohere reranking")
        
        self.model = model
        
        try:
            import cohere
            self.client = cohere.Client(api_key)
            logger.info(f"CohereReranker initialized with model: {model}")
        except ImportError:
            raise ImportError("cohere package required. Install with: pip install cohere")
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[RerankResult]:
        """Rerank using Cohere API."""
        if not documents:
            return []
        
        # Call Cohere Rerank API
        response = self.client.rerank(
            query=query,
            documents=documents,
            top_n=min(top_k, len(documents)),
            model=self.model
        )
        
        # Convert to our format
        results = [
            RerankResult(
                index=result.index,
                score=result.relevance_score,
                text=documents[result.index]
            )
            for result in response.results
        ]
        
        logger.info(f"Cohere reranked {len(documents)} documents, returning top {len(results)}")
        return results
    
    def get_model_info(self) -> dict:
        """Get model metadata."""
        return {
            "name": self.model,
            "type": "api",
            "provider": "cohere"
        }
    
    def close(self):
        """Close API client."""
        if hasattr(self.client, 'close'):
            self.client.close()
