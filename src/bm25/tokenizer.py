"""
Tokenizer for BM25 text processing.

Tokenization pipeline:
1. Lowercase conversion
2. Extract alphanumeric words (including hyphens)
3. Filter stopwords (common English words)
4. Filter pure numbers
5. Apply stemming (reduce to root form: "architectures" → "architectur")
6. Return list of meaningful tokens

Future enhancements (optional):
- Multi-language support
"""

import re
from typing import List

from .stemmer import stem

# English stopwords (based on Elasticsearch/Lucene standard list)
# These are common words that don't help with ranking
STOPWORDS = frozenset([
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by',
    'for', 'if', 'in', 'into', 'is', 'it',
    'no', 'not', 'of', 'on', 'or', 'such',
    'that', 'the', 'their', 'then', 'there', 'these',
    'they', 'this', 'to', 'was', 'will', 'with'
])


def tokenize(text: str) -> List[str]:
    """
    Tokenize text for BM25 scoring with stopword removal.
    
    Process:
    1. Convert to lowercase
    2. Extract words (alphanumeric + hyphens preserved)
    3. Remove stopwords (common English words like 'the', 'is', 'and')
    4. Remove pure numbers (keep alphanumeric terms like 'bm25', 'postgresql')
    5. Apply stemming (reduce to root: "searching" → "search")
    6. Filter empty strings
    
    Args:
        text: Input text to tokenize
        
    Returns:
        List of lowercase tokens without stopwords
        
    Examples:
        >>> tokenize("Kubernetes-based deployment strategies!")
        ['kubernet', 'base', 'deploy', 'strategi']
        
        >>> tokenize("PostgreSQL 15.3 with pgvector")
        ['postgresql', 'pgvector']
        
        >>> tokenize("BM25 scores: 0.95, 0.87, 0.73")
        ['bm25', 'score']
        
        >>> tokenize("   ")
        []
    """
    if not text:
        return []
    
    # Lowercase
    text = text.lower()
    
    # Extract words: alphanumeric + hyphens within words
    # Pattern: word boundary + alphanumeric + optional hyphen + alphanumeric + word boundary
    tokens = re.findall(r'\b[a-z0-9]+(?:-[a-z0-9]+)*\b', text)
    
    # Remove stopwords and pure numbers (keep alphanumeric like "bm25", "postgresql")
    tokens = [
        t for t in tokens 
        if t not in STOPWORDS and not re.match(r'^[0-9-]+$', t)
    ]
    
    # Apply stemming to reduce words to root form
    # "architectures" → "architectur", "searching" → "search"
    tokens = [stem(t) for t in tokens]
    
    return tokens
