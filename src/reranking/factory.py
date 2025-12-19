"""
Factory to create reranker instances based on configuration.
"""

from typing import Optional
import os
import logging

from .base import BaseReranker
from .local import LocalCrossEncoderReranker
from .cohere import CohereReranker
from .gemini import GeminiReranker

logger = logging.getLogger(__name__)


class RerankingFactory:
    """Factory to create reranker instances based on configuration."""
    
    _instance: Optional[BaseReranker] = None  # Singleton cache
    
    @classmethod
    def create(cls, force_reload: bool = False) -> Optional[BaseReranker]:
        """
        Create reranker based on environment configuration.
        
        Config (env vars):
            RERANKER_ENABLED: "true" to enable reranking
            RERANKER_TYPE: "gemini" | "local" | "cohere" (default: gemini)
            RERANKER_MODEL: Model identifier (type-specific)
            
        Supported types:
            - gemini: LLM-based reranking with Gemini (recommended, default)
            - local: Cross-encoder models from HuggingFace (fast, runs locally)
            - cohere: Cohere's rerank API (requires API key)
        
        Args:
            force_reload: If True, recreate instance even if cached
            
        Returns:
            Reranker instance, or None if disabled
        """
        # Return cached instance
        if cls._instance is not None and not force_reload:
            logger.info(f"Returning cached reranker instance: {cls._instance}")
            return cls._instance
        
        # Check if enabled
        enabled_value = os.getenv("RERANKER_ENABLED")
        if not enabled_value:
            raise ValueError("RERANKER_ENABLED environment variable is required")
        enabled = enabled_value.lower() == "true"
        logger.info(f"Reranker config check: RERANKER_ENABLED={enabled_value} (enabled={enabled})")
        
        if not enabled:
            return None
        
        reranker_type = os.getenv("RERANKER_TYPE")
        if not reranker_type:
            raise ValueError("RERANKER_TYPE environment variable is required when reranking enabled")
        reranker_type = reranker_type.lower()
        
        model = os.getenv("RERANKER_MODEL")
        if not model:
            raise ValueError("RERANKER_MODEL environment variable is required when reranking enabled")
        
        # Create based on type
        try:
            if reranker_type == "gemini":
                # Gemini LLM-based reranking
                logger.info(f"Creating Gemini LLM reranker: {model}")
                # Support both GOOGLE_CLOUD_PROJECT and GCP_PROJECT_ID env vars
                project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
                location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GCP_REGION")
                if not location:
                    raise ValueError("GCP_REGION or GOOGLE_CLOUD_LOCATION environment variable is required")
                cls._instance = GeminiReranker(
                    model_name=model,
                    project_id=project_id,
                    location=location
                )
            
            elif reranker_type == "local":
                # Cross-encoder models (fast, runs locally, lower quality)
                if not model:
                    model = "cross-encoder/ms-marco-MiniLM-L-12-v2"  # Default
                logger.info(f"Creating local cross-encoder reranker: {model}")
                cls._instance = LocalCrossEncoderReranker(model_name=model)
            
            elif reranker_type == "cohere":
                # Cohere rerank API
                if not model:
                    model = "rerank-english-v3.0"
                logger.info(f"Creating Cohere reranker: {model}")
                cls._instance = CohereReranker(model=model)
            
            else:
                raise ValueError(
                    f"Unknown reranker type: {reranker_type}. "
                    f"Valid options: gemini, local, cohere"
                )
        
        except Exception as e:
            logger.error(f"Failed to create reranker ({reranker_type}): {e}")
            raise
        
        return cls._instance
    
    @classmethod
    def cleanup(cls):
        """Cleanup cached reranker instance."""
        if cls._instance is not None:
            logger.info("Cleaning up reranker instance")
            cls._instance.close()
            cls._instance = None
