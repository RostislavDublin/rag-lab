"""
Authentication manager for tests with automatic token refresh.

Provides automatic retry on 401 errors with token refresh,
making long-running integration tests seamless.
"""

import subprocess
import sys
from pathlib import Path
from functools import wraps
import requests


class TokenManager:
    """Manages OAuth tokens with automatic refresh on expiration."""
    
    def __init__(self):
        self._token = None
        self._token_script = Path(__file__).parent.parent / "scripts" / "get_user_token.py"
    
    def get_token(self, force_refresh: bool = False) -> str:
        """
        Get valid access token, refreshing if needed.
        
        Args:
            force_refresh: Force token refresh even if cached
        
        Returns:
            Valid JWT token
        """
        if not force_refresh and self._token:
            return self._token
        
        # Call get_user_token.py which handles caching and refresh
        result = subprocess.run(
            [sys.executable, str(self._token_script)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120
        )
        
        self._token = result.stdout.strip()
        return self._token
    
    def get_headers(self, force_refresh: bool = False) -> dict:
        """
        Get Authorization headers with valid token.
        
        Args:
            force_refresh: Force token refresh even if cached
        
        Returns:
            Dict with Authorization header
        """
        token = self.get_token(force_refresh=force_refresh)
        return {"Authorization": f"Bearer {token}"}
    
    def request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 1,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with automatic retry on 401 (token refresh).
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: Request URL
            max_retries: Max number of retries after 401 (default 1)
            **kwargs: Additional arguments for requests (json, files, timeout, etc.)
        
        Returns:
            Response object
        
        Raises:
            requests.HTTPError: If request fails after retries
        
        Example:
            >>> tm = TokenManager()
            >>> resp = tm.request_with_retry("POST", f"{API_BASE}/v1/query", 
            ...                              json={"query": "test"}, timeout=30)
        """
        # Inject auth headers if not provided
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        
        # Add Authorization header (will be refreshed on retry)
        kwargs["headers"]["Authorization"] = f"Bearer {self.get_token()}"
        
        for attempt in range(max_retries + 1):
            response = requests.request(method, url, **kwargs)
            
            # Success or non-401 error - return immediately
            if response.status_code != 401:
                return response
            
            # 401 - token expired, refresh and retry
            if attempt < max_retries:
                # Force token refresh
                new_token = self.get_token(force_refresh=True)
                kwargs["headers"]["Authorization"] = f"Bearer {new_token}"
                continue
            
            # Max retries exhausted - return 401 response
            return response
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with auto-retry on 401."""
        return self.request_with_retry("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with auto-retry on 401."""
        return self.request_with_retry("POST", url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """DELETE request with auto-retry on 401."""
        return self.request_with_retry("DELETE", url, **kwargs)
    
    def put(self, url: str, **kwargs) -> requests.Response:
        """PUT request with auto-retry on 401."""
        return self.request_with_retry("PUT", url, **kwargs)


# Global singleton for tests
_token_manager = None

def get_token_manager() -> TokenManager:
    """Get global TokenManager singleton."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


def with_auto_refresh(func):
    """
    Decorator to automatically refresh token on 401 errors.
    
    Usage:
        @with_auto_refresh
        def my_api_call():
            response = requests.get(f"{API_BASE}/v1/documents", 
                                   headers=auth_headers)
            return response
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tm = get_token_manager()
        
        # First attempt
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response.status_code != 401:
                raise
        
        # 401 - refresh token and retry
        tm.get_token(force_refresh=True)
        return func(*args, **kwargs)
    
    return wrapper
