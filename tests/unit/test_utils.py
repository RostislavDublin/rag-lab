"""Unit tests for utility functions"""

import hashlib
from pathlib import Path

import pytest

from src.utils import calculate_file_hash


class TestFileHash:
    """Test file hash calculation consistency"""
    
    def test_hash_from_bytes(self):
        """Test hash calculation from bytes"""
        content = b"test content"
        expected = hashlib.sha256(content).hexdigest()
        
        result = calculate_file_hash(content)
        
        assert result == expected
        assert len(result) == 64  # SHA256 = 256 bits = 64 hex chars
    
    def test_hash_from_file_path_str(self, tmp_path):
        """Test hash calculation from file path (string)"""
        test_file = tmp_path / "test.txt"
        content = b"test content for file"
        test_file.write_bytes(content)
        
        expected = hashlib.sha256(content).hexdigest()
        result = calculate_file_hash(str(test_file))
        
        assert result == expected
    
    def test_hash_from_file_path_object(self, tmp_path):
        """Test hash calculation from Path object"""
        test_file = tmp_path / "test.pdf"
        content = b"binary PDF content"
        test_file.write_bytes(content)
        
        expected = hashlib.sha256(content).hexdigest()
        result = calculate_file_hash(test_file)
        
        assert result == expected
    
    def test_hash_consistency_multiple_calls(self, tmp_path):
        """Test that same file always produces same hash"""
        test_file = tmp_path / "consistent.pdf"
        content = b"consistent content"
        test_file.write_bytes(content)
        
        hash1 = calculate_file_hash(test_file)
        hash2 = calculate_file_hash(test_file)
        hash3 = calculate_file_hash(content)  # From bytes
        
        assert hash1 == hash2 == hash3
    
    def test_hash_different_for_different_content(self):
        """Test that different content produces different hash"""
        content1 = b"content one"
        content2 = b"content two"
        
        hash1 = calculate_file_hash(content1)
        hash2 = calculate_file_hash(content2)
        
        assert hash1 != hash2
    
    def test_hash_binary_mode_consistency(self, tmp_path):
        """Test that binary mode reading is consistent"""
        test_file = tmp_path / "binary_test.dat"
        # Use bytes that would differ in text mode (line endings)
        content = b"line1\nline2\nline3\n"
        test_file.write_bytes(content)
        
        # Calculate from file (uses 'rb' mode internally)
        hash_from_file = calculate_file_hash(test_file)
        
        # Calculate from bytes directly
        hash_from_bytes = calculate_file_hash(content)
        
        # Should be identical (proves we're using binary mode)
        assert hash_from_file == hash_from_bytes
    
    def test_hash_with_real_fixture(self):
        """Test hash calculation with real test fixture"""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "documents" / "rag_architecture_guide.txt"
        
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")
        
        # Calculate hash twice - should be identical
        hash1 = calculate_file_hash(fixture_path)
        hash2 = calculate_file_hash(fixture_path)
        
        assert hash1 == hash2
        assert len(hash1) == 64
        
        # Also verify manual calculation matches
        with open(fixture_path, "rb") as f:
            manual_hash = hashlib.sha256(f.read()).hexdigest()
        
        assert hash1 == manual_hash
