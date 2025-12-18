"""
BM25 index builder - aggregates term frequencies from document chunks.

Creates minimal document-level BM25 index for GCS storage.
"""

import logging
from collections import defaultdict
from typing import Dict, List

from .tokenizer import tokenize

logger = logging.getLogger(__name__)


def build_bm25_index(chunks_texts: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Build document-level BM25 index from chunk texts.
    
    Aggregates term frequencies across all chunks to create a single
    document-level term frequency dictionary.
    
    Args:
        chunks_texts: List of chunk text strings
    
    Returns:
        Dict with structure:
        {
            "term_frequencies": {
                "term1": count1,
                "term2": count2,
                ...
            }
        }
    
    Example:
        >>> chunks = ["Kubernetes pod deployment", "pod configuration yaml"]
        >>> index = build_bm25_index(chunks)
        >>> print(index)
        {
            "term_frequencies": {
                "kubernetes": 1,
                "pod": 2,
                "deployment": 1,
                "configuration": 1,
                "yaml": 1
            }
        }
    """
    # Aggregate term frequencies across all chunks
    term_frequencies = defaultdict(int)
    
    for chunk_text in chunks_texts:
        tokens = tokenize(chunk_text)
        
        # Count term occurrences in this chunk
        for term in tokens:
            term_frequencies[term] += 1
    
    # Convert defaultdict to regular dict (for JSON serialization)
    result = {
        "term_frequencies": dict(term_frequencies)
    }
    
    logger.debug(f"Built BM25 index: {len(result['term_frequencies'])} unique terms from {len(chunks_texts)} chunks")
    
    return result
