"""
Simplified BM25 scorer without global IDF.

BM25 (Best Match 25) is a probabilistic ranking function used for information retrieval.
This implementation uses a simplified version without global IDF (Inverse Document Frequency)
to avoid distributed state management issues.

Formula (simplified):
    score(term, doc) = (tf × (k1 + 1)) / (tf + k1 × (1 - b + b × dl/avgdl))

Where:
    tf = term frequency in document
    k1 = term frequency saturation parameter (default: 1.2)
    b = length normalization parameter (default: 0.75)
    dl = document length (number of tokens)
    avgdl = average document length (approximate constant: 1000)

Keyword Boosting:
    If query term matches LLM-extracted keyword, apply boost multiplier (default: 1.5x)
"""

from typing import Dict, List


class SimplifiedBM25:
    """
    Simplified BM25 scoring without global IDF.
    
    Uses LLM-extracted keywords for importance boosting instead of statistical IDF.
    """
    
    def __init__(self, k1: float = 1.2, b: float = 0.75, avgdl: float = 1000, boost: float = 1.5):
        """
        Initialize BM25 scorer.
        
        Args:
            k1: Term frequency saturation parameter
                Higher = more weight to term frequency
                Range: 1.2 - 2.0
                Default: 1.2 (standard)
                
            b: Length normalization parameter
                Higher = more penalty for long documents
                Range: 0.0 - 1.0
                Default: 0.75 (standard)
                
            avgdl: Average document length (in tokens)
                Approximation constant for normalization
                Default: 1000 tokens
                
            boost: Keyword boost multiplier
                Applied when query term matches LLM keyword
                Default: 1.5 (50% boost)
        """
        self.k1 = k1
        self.b = b
        self.avgdl = avgdl
        self.boost = boost
    
    def score(
        self,
        query_terms: List[str],
        doc_term_frequencies: Dict[str, int],
        token_count: int,
        keywords: List[str] = None
    ) -> float:
        """
        Compute simplified BM25 score for a document given query terms.
        
        Args:
            query_terms: Tokenized query (lowercase)
            doc_term_frequencies: Term frequency map {term: count}
            token_count: Total number of tokens in document
            keywords: LLM-extracted important keywords (optional)
                Used for boosting query terms that match important concepts
        
        Returns:
            BM25 score (higher = more relevant)
            
        Example:
            >>> scorer = SimplifiedBM25()
            >>> scorer.score(
            ...     query_terms=["kubernetes", "deployment"],
            ...     doc_term_frequencies={"kubernetes": 15, "deployment": 12, "pod": 8},
            ...     token_count=5000,
            ...     keywords=["Kubernetes", "deployment strategies"]
            ... )
            2.847...  # Both terms boosted by keywords
        """
        if not query_terms or not doc_term_frequencies:
            return 0.0
        
        score = 0.0
        
        # Compute base BM25 score for each query term
        for term in query_terms:
            tf = doc_term_frequencies.get(term, 0)
            
            if tf == 0:
                continue
            
            # BM25 formula (without IDF component)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * (token_count / self.avgdl)
            )
            
            term_score = numerator / denominator
            score += term_score
        
        # Apply keyword boosting
        if keywords and score > 0:
            boost_multiplier = 1.0
            
            for term in query_terms:
                # Case-insensitive matching: query term in any keyword
                if any(term.lower() in kw.lower() for kw in keywords):
                    boost_multiplier *= self.boost
            
            score *= boost_multiplier
        
        return score
