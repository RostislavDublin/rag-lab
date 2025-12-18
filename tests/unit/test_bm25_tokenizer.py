"""
Unit tests for BM25 tokenizer with Snowball stemming.
"""

import pytest
from src.bm25.tokenizer import tokenize


class TestTokenizer:
    """Test tokenization logic with Snowball stemming applied"""
    
    def test_basic_tokenization(self):
        """Test basic word extraction with Snowball stemming"""
        text = "Kubernetes deployment strategies"
        tokens = tokenize(text)
        # Snowball stemming: "strategies" → "strategi", "deployment" → "deploy", "kubernetes" → "kubernet"
        assert "kubernet" in tokens
        assert "deploy" in tokens
        assert "strategi" in tokens
    
    def test_lowercase_conversion(self):
        """Test that all tokens are lowercased"""
        text = "PostgreSQL Cloud SQL"
        tokens = tokenize(text)
        assert "postgresql" in tokens
        assert "cloud" in tokens
        assert "sql" in tokens
    
    def test_hyphenated_words(self):
        """Test preservation of hyphens within words, then Snowball stemming"""
        text = "kubernetes-based blue-green deployment"
        tokens = tokenize(text)
        # Hyphenated words are stemmed as single units
        assert "kubernetes-bas" in tokens
        assert "blue-green" in tokens
        assert "deploy" in tokens  # Snowball handles this
    
    def test_punctuation_removal(self):
        """Test that punctuation is removed before stemming"""
        text = "deployment! strategies? rolling-updates."
        tokens = tokenize(text)
        # Snowball stemming applied
        assert "deploy" in tokens
        assert "strategi" in tokens
        assert "rolling-upd" in tokens  # Snowball: "rolling-updates" → "rolling-upd"
    
    def test_numbers(self):
        """Test that pure numbers are filtered out"""
        text = "PostgreSQL 15.3 with Python 3.11"
        tokens = tokenize(text)
        # Pure numbers are filtered out
        assert "15" not in tokens
        assert "3" not in tokens
        assert "11" not in tokens
        # But alphanumeric terms are kept
        assert "postgresql" in tokens
        assert "python" in tokens
    
    def test_empty_string(self):
        """Test empty string returns empty list"""
        assert tokenize("") == []
        assert tokenize("   ") == []
        assert tokenize("\n\t") == []
    
    def test_special_characters(self):
        """Test handling of special characters with stemming"""
        text = "user@example.com file_name.txt path/to/file"
        tokens = tokenize(text)
        # @ and _ and . and / split tokens (only hyphens preserved)
        # "to" is a stopword and filtered out
        assert "user" in tokens
        assert "exampl" in tokens  # "example" → "exampl"
        assert "com" in tokens
        assert "txt" in tokens
        assert "path" in tokens
        assert "to" not in tokens  # Stopword removed
        assert "file" in tokens
    
    def test_unicode_handling(self):
        """Test basic unicode text (ASCII only for now)"""
        text = "Kubernetes deployment"
        tokens = tokenize(text)
        assert "kubernet" in tokens
        assert "deploy" in tokens  # Snowball handles this
    
    def test_mixed_content(self):
        """Test realistic mixed content with Snowball stemming"""
        text = "Deploy Kubernetes 1.28.3 using kubectl apply -f deployment.yaml"
        tokens = tokenize(text)
        # Both "deploy" and "deployment" → "deploy" (appears twice)
        assert tokens.count("deploy") == 2
        assert "kubernet" in tokens  # "kubernetes" → "kubernet"
        # Pure numbers filtered out
        assert "1" not in tokens
        assert "28" not in tokens
        # But meaningful terms kept
        assert "kubectl" in tokens
        assert "appli" in tokens  # "apply" → "appli"
        assert "yaml" in tokens
