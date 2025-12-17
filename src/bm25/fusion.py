"""
RRF (Reciprocal Rank Fusion) for combining multiple rankings.

RRF is a simple and effective method for combining results from multiple ranking systems.
It doesn't require normalization of scores and is robust to outliers.

Formula:
    RRF(item, k=60) = Σ 1/(k + rank_i(item))

Where:
    k = constant (default: 60, from literature)
    rank_i = rank of item in i-th ranking (1-based)

Reference: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
"""

from typing import List, Dict, Any


def reciprocal_rank_fusion(
    rankings: List[List[Dict[str, Any]]],
    k: int = 60,
    item_key: str = 'chunk_id'
) -> List[Dict[str, Any]]:
    """
    Combine multiple rankings using Reciprocal Rank Fusion.
    
    Args:
        rankings: List of ranked result lists
            Each ranking is a list of items (dicts)
            Items must have an identifier field (default: 'chunk_id')
            
        k: RRF constant (default: 60)
            Standard value from literature
            Prevents divide-by-zero and controls fusion behavior
            
        item_key: Key to use for item identification (default: 'chunk_id')
    
    Returns:
        Combined ranking sorted by RRF score (descending)
        Each item includes 'rrf_score' field
        
    Example:
        >>> vector_ranking = [
        ...     {'chunk_id': 1, 'similarity': 0.85},
        ...     {'chunk_id': 2, 'similarity': 0.80},
        ...     {'chunk_id': 3, 'similarity': 0.75}
        ... ]
        >>> bm25_ranking = [
        ...     {'chunk_id': 3, 'bm25': 15.2},
        ...     {'chunk_id': 1, 'bm25': 12.8},
        ...     {'chunk_id': 5, 'bm25': 10.1}
        ... ]
        >>> fused = reciprocal_rank_fusion([vector_ranking, bm25_ranking])
        >>> [item['chunk_id'] for item in fused]
        [1, 3, 2, 5]  # Chunk 1 and 3 appear in both, ranked higher
    """
    if not rankings:
        return []
    
    # Compute RRF scores
    rrf_scores: Dict[Any, float] = {}
    
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            item_id = item[item_key]
            rrf_score = 1.0 / (k + rank)
            rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + rrf_score
    
    # Collect all unique items
    all_items: Dict[Any, Dict[str, Any]] = {}
    for ranking in rankings:
        for item in ranking:
            item_id = item[item_key]
            if item_id not in all_items:
                all_items[item_id] = item.copy()
    
    # Sort by RRF score
    sorted_items = sorted(
        all_items.values(),
        key=lambda x: rrf_scores[x[item_key]],
        reverse=True
    )
    
    # Add RRF scores to results
    for item in sorted_items:
        item['rrf_score'] = rrf_scores[item[item_key]]
    
    return sorted_items
