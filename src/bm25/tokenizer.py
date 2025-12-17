"""
Tokenizer for BM25 text processing.

Simple tokenization pipeline:
1. Lowercase conversion
2. Extract alphanumeric words (including hyphens)
3. Return list of tokens

Future enhancements (optional):
- Stopwords removal
- Stemming (Porter stemmer)
- Multi-language support
"""

import re
from typing import List


def tokenize(text: str) -> List[str]:
    """
    Tokenize text for BM25 scoring.
    
    Process:
    1. Convert to lowercase
    2. Extract words (alphanumeric + hyphens preserved)
    3. Filter empty strings
    
    Args:
        text: Input text to tokenize
        
    Returns:
        List of lowercase tokens
        
    Examples:
        >>> tokenize("Kubernetes-based deployment strategies!")
        ['kubernetes-based', 'deployment', 'strategies']
        
        >>> tokenize("PostgreSQL 15.3 with pgvector")
        ['postgresql', '15', '3', 'with', 'pgvector']
        
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
    
    return tokens
