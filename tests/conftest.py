"""Pytest configuration for E2E tests"""

import pytest
import jwt
from datetime import datetime, timedelta


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Skip cleanup of test documents after E2E tests (for debugging)"
    )


@pytest.fixture(scope="session")
def test_auth_token():
    """
    Generate a test JWT token for authenticated API calls.
    
    In dev mode (GOOGLE_CLIENT_ID empty), src/auth.py accepts any JWT.
    This generates a simple token with test user email.
    """
    payload = {
        "email": "javaisforever@gmail.com",  # Whitelisted test user
        "sub": "test_user_12345",
        "name": "Test User",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    
    # Create JWT with HS256 (dev mode doesn't verify signature)
    token = jwt.encode(payload, "test_secret", algorithm="HS256")
    return token


@pytest.fixture(scope="session")
def auth_headers(test_auth_token):
    """HTTP headers with Bearer token for authenticated requests"""
    return {
        "Authorization": f"Bearer {test_auth_token}"
    }

