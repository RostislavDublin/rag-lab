"""
Reranking module for RAG Lab.

Usage:
    # Get reranker (auto-configured from env):
    from reranking import get_reranker
    
    reranker = get_reranker()
    if reranker:
        results = reranker.rerank(query, documents, top_k=5)
    
    # Or create specific implementation:
    from reranking import LocalCrossEncoderReranker
    
    reranker = LocalCrossEncoderReranker("BAAI/bge-reranker-base")
    results = reranker.rerank(query, documents, top_k=5)
"""

from typing import Optional
from .base import BaseReranker, RerankResult
from .local import LocalCrossEncoderReranker
from .cohere import CohereReranker
from .gemini import GeminiReranker
from .factory import RerankingFactory


def get_reranker(force_reload: bool = False) -> Optional[BaseReranker]:
    """
    Get configured reranker instance (factory convenience function).
    
    Returns None if reranking disabled via RERANKER_ENABLED=false
    """
    return RerankingFactory.create(force_reload=force_reload)


__all__ = [
    'BaseReranker',
    'RerankResult',
    'LocalCrossEncoderReranker',
    'CohereReranker',
    'GeminiReranker',
    'get_reranker',
]
