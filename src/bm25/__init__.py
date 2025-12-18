"""
BM25 (Best Match 25) ranking algorithm for hybrid search.

This module implements a simplified BM25 scoring algorithm without global IDF
(Inverse Document Frequency) to avoid distributed state management issues.

Components:
- tokenizer: Text tokenization for term extraction
- scorer: Simplified BM25 scoring with keyword boosting
- fusion: RRF (Reciprocal Rank Fusion) for combining rankings
- index_builder: Document-level term frequency aggregation
- llm_extraction: LLM-based summary and keyword extraction

Key simplification: No global IDF statistics
- Avoids race conditions in distributed uploads
- No database locks on global stats table
- LLM-extracted keywords compensate for missing IDF
"""

from .tokenizer import tokenize
from .stemmer import stem
from .scorer import SimplifiedBM25
from .fusion import reciprocal_rank_fusion
from .index_builder import build_bm25_index
from .llm_extraction import extract_summary_and_keywords

__all__ = [
    "tokenize",
    "stem",
    "SimplifiedBM25",
    "reciprocal_rank_fusion",
    "build_bm25_index",
    "extract_summary_and_keywords",
]
