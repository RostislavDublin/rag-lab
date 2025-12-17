"""
Unit tests for SimplifiedBM25 scorer.
"""

import pytest
from src.bm25.scorer import SimplifiedBM25


class TestSimplifiedBM25:
    """Test BM25 scoring logic"""
    
    def test_basic_scoring(self):
        """Test basic BM25 scoring without keywords"""
        scorer = SimplifiedBM25()
        
        score = scorer.score(
            query_terms=["kubernetes", "deployment"],
            doc_term_frequencies={"kubernetes": 10, "deployment": 5, "pod": 3},
            token_count=1000
        )
        
        assert score > 0
        assert isinstance(score, float)
    
    def test_zero_score_no_matches(self):
        """Test that score is zero when no query terms match"""
        scorer = SimplifiedBM25()
        
        score = scorer.score(
            query_terms=["nonexistent", "terms"],
            doc_term_frequencies={"kubernetes": 10, "deployment": 5},
            token_count=1000
        )
        
        assert score == 0.0
    
    def test_keyword_boosting(self):
        """Test that LLM keywords boost the score"""
        scorer = SimplifiedBM25(boost=1.5)
        
        # Score without keywords
        score_without = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=1000,
            keywords=None
        )
        
        # Score with matching keyword
        score_with = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=1000,
            keywords=["Kubernetes", "DevOps"]
        )
        
        assert score_with > score_without
        assert score_with == pytest.approx(score_without * 1.5, rel=0.01)
    
    def test_multiple_keyword_boosting(self):
        """Test boosting with multiple matching keywords"""
        scorer = SimplifiedBM25(boost=1.5)
        
        score = scorer.score(
            query_terms=["kubernetes", "deployment"],
            doc_term_frequencies={"kubernetes": 10, "deployment": 5},
            token_count=1000,
            keywords=["Kubernetes", "deployment strategies"]
        )
        
        # Both terms should be boosted: 1.5 * 1.5 = 2.25x
        score_base = scorer.score(
            query_terms=["kubernetes", "deployment"],
            doc_term_frequencies={"kubernetes": 10, "deployment": 5},
            token_count=1000,
            keywords=None
        )
        
        assert score == pytest.approx(score_base * (1.5 ** 2), rel=0.01)
    
    def test_length_normalization(self):
        """Test that longer documents get penalized"""
        scorer = SimplifiedBM25(b=0.75)
        
        # Same term frequency, different document lengths
        score_short = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=500  # Shorter than avgdl=1000
        )
        
        score_long = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=2000  # Longer than avgdl=1000
        )
        
        # Shorter document should score higher (less penalty)
        assert score_short > score_long
    
    def test_term_frequency_saturation(self):
        """Test k1 parameter controls TF saturation"""
        scorer = SimplifiedBM25(k1=1.2)
        
        # Score with low TF
        score_low_tf = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 1},
            token_count=1000
        )
        
        # Score with high TF
        score_high_tf = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 100},
            token_count=1000
        )
        
        # High TF should score higher, but not 100x due to saturation
        assert score_high_tf > score_low_tf
        assert score_high_tf < score_low_tf * 10  # Saturation effect
    
    def test_empty_query(self):
        """Test handling of empty query"""
        scorer = SimplifiedBM25()
        
        score = scorer.score(
            query_terms=[],
            doc_term_frequencies={"kubernetes": 10},
            token_count=1000
        )
        
        assert score == 0.0
    
    def test_empty_document(self):
        """Test handling of empty document"""
        scorer = SimplifiedBM25()
        
        score = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={},
            token_count=0
        )
        
        assert score == 0.0
    
    def test_case_insensitive_keyword_matching(self):
        """Test that keyword matching is case-insensitive"""
        scorer = SimplifiedBM25(boost=1.5)
        
        score_lower = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=1000,
            keywords=["Kubernetes"]  # Uppercase
        )
        
        score_upper = scorer.score(
            query_terms=["kubernetes"],
            doc_term_frequencies={"kubernetes": 10},
            token_count=1000,
            keywords=["kubernetes"]  # Lowercase
        )
        
        assert score_lower == score_upper
    
    def test_partial_keyword_matching(self):
        """Test that query terms match within keywords"""
        scorer = SimplifiedBM25(boost=1.5)
        
        # "deployment" matches "deployment strategies"
        score = scorer.score(
            query_terms=["deployment"],
            doc_term_frequencies={"deployment": 10},
            token_count=1000,
            keywords=["Kubernetes", "deployment strategies"]
        )
        
        score_no_boost = scorer.score(
            query_terms=["deployment"],
            doc_term_frequencies={"deployment": 10},
            token_count=1000,
            keywords=None
        )
        
        assert score > score_no_boost
