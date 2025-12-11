"""Utility functions for RAG system"""

import hashlib
from pathlib import Path
from typing import Union


def calculate_file_hash(file_path_or_content: Union[str, Path, bytes]) -> str:
    """
    Calculate SHA256 hash of a file
    
    Args:
        file_path_or_content: File path (str/Path) or file content (bytes)
    
    Returns:
        Hexadecimal hash string (64 characters)
    
    Examples:
        >>> calculate_file_hash("/path/to/file.pdf")
        'a1b2c3d4...'
        
        >>> calculate_file_hash(b"binary content")
        'e5f6g7h8...'
    """
    if isinstance(file_path_or_content, bytes):
        # Content provided directly
        content = file_path_or_content
    else:
        # Read from file path
        path = Path(file_path_or_content)
        with open(path, "rb") as f:  # Always binary mode!
            content = f.read()
    
    return hashlib.sha256(content).hexdigest()
