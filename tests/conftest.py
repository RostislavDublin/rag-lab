"""Pytest configuration for E2E tests"""

import pytest
import sys
from pathlib import Path

# Add project root to path for src imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add tests directory to path for auth_manager import
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))

from auth_manager import get_token_manager


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Skip cleanup of test documents after E2E tests (for debugging)"
    )


@pytest.fixture(scope="session")
def token_manager():
    """
    Global TokenManager for all tests.
    
    Handles:
    - Token caching (~/.rag-lab-refresh-token.json)
    - Silent token refresh when expired
    - Automatic retry on 401 errors
    
    First test run: Opens browser for OAuth (gets refresh_token)
    Subsequent runs: Silent refresh (no user interaction)
    """
    return get_token_manager()


@pytest.fixture(scope="session")
def test_auth_token(token_manager):
    """
    Get valid JWT token using TokenManager.
    
    This will:
    1. Check cache for valid token
    2. Refresh if expired (using refresh_token)
    3. Run OAuth flow if needed (browser, only first time)
    """
    return token_manager.get_token()


@pytest.fixture(scope="session")
def auth_headers(token_manager):
    """
    HTTP headers with Bearer token for authenticated requests.
    
    Note: For long-running tests, prefer using token_manager.get()/.post()
    which automatically refresh on 401 errors.
    """
    return token_manager.get_headers()