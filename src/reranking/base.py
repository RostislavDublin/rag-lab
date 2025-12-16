"""
Abstract base class for reranking implementations.

All rerankers must implement this interface to be swappable.
"""

from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass


@dataclass
class RerankResult:
    """Single reranked result with score"""
    index: int           # Original index in candidates list
    score: float        # Relevance score (0-1, higher = more relevant)
    text: str           # Document text (for convenience)
    reasoning: str = "" # LLM explanation of why this document is relevant (Gemini only)


class BaseReranker(ABC):
    """
    Abstract base class for reranking implementations.
    
    All rerankers must implement this interface to be swappable.
    """
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[RerankResult]:
        """
        Rerank documents by relevance to query.
        
        Args:
            query: Search query text
            documents: List of document texts to rerank
            top_k: Number of top results to return
            
        Returns:
            List of RerankResult, sorted by score (descending)
            Length = min(top_k, len(documents))
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> dict:
        """
        Get information about the reranker model.
        
        Returns:
            Dict with keys: name, type, version, parameters
        """
        pass
    
    def close(self):
        """Optional cleanup (close API clients, free GPU memory, etc.)"""
        pass
