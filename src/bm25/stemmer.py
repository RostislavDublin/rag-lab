"""
Snowball Stemmer for English (via NLTK).

Uses the Snowball stemming algorithm (improved Porter2 stemmer):
https://snowballstem.org/

Snowball is more accurate than original Porter stemmer:
- Better handling of word endings
- More consistent stem generation
- Used by Elasticsearch, Solr, Lucene

Examples:
- "architectures" → "architectur"
- "strategies" → "strategi"
- "communication" → "commun"
- "running" → "run"
"""

from nltk.stem.snowball import SnowballStemmer

# Initialize stemmer once (thread-safe, reusable)
_stemmer = SnowballStemmer('english')


def stem(word: str) -> str:
    """
    Stem a single word using Snowball algorithm.
    
    Args:
        word: Lowercase word to stem
        
    Returns:
        Stemmed word
        
    Examples:
        >>> stem("architectures")
        'architectur'
        >>> stem("searching")
        'search'
        >>> stem("communication")
        'commun'
    """
    return _stemmer.stem(word)
