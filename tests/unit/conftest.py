"""Unit test configuration - mocks for isolated testing"""

import pytest
import jwt
from unittest.mock import Mock, patch
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env.local FIRST (before any imports that need env vars)
env_file = Path(__file__).parent.parent.parent / ".env.local"
if env_file.exists():
    load_dotenv(env_file)

# CRITICAL: Set env vars BEFORE importing src.auth
# auth.py reads ALLOWED_USERS at module level (on import)
# Must patch os.environ before any test file imports auth module
os.environ.setdefault("ALLOWED_USERS", "javaisforever@gmail.com,test@example.com")
os.environ.setdefault("AUDIENCE", "test-audience.apps.googleusercontent.com")
os.environ.setdefault("JWKS_URL", "https://www.googleapis.com/oauth2/v3/certs")
os.environ.setdefault("ISSUER", "https://accounts.google.com")


@pytest.fixture(scope="session", autouse=True)
def setup_unit_test_environment():
    """
    Setup environment for unit tests.
    
    Unit tests use mocked JWT validation - no real JWKS calls.
    E2E/integration tests use real tokens and real API.
    """
    # Ensure environment variables are set before any imports
    # (auth.py reads these at module level)
    pass


@pytest.fixture(autouse=True)
def mock_jwks_validation():
    """
    Mock PyJWKClient and jwt.decode for each unit test.
    
    This ensures unit tests don't make real HTTP requests to JWKS endpoints
    and can test with simple HS256 tokens instead of RS256.
    """
    # Save original jwt.decode BEFORE patching
    import jwt as pyjwt
    original_jwt_decode = pyjwt.decode
    
    with patch("src.auth.PyJWKClient") as mock_jwks_client, \
         patch("src.auth.jwt.decode") as mock_jwt_decode:
        
        # Mock JWKS client to return a valid signing key
        mock_signing_key = Mock()
        mock_signing_key.key = "test_public_key"
        mock_client_instance = Mock()
        mock_client_instance.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_jwks_client.return_value = mock_client_instance
        
        # Mock jwt.decode to decode test tokens without signature verification
        def decode_side_effect(token, *args, **kwargs):
            # Use ORIGINAL jwt.decode (not mocked) to avoid recursion
            return original_jwt_decode(token, options={"verify_signature": False})
        
        mock_jwt_decode.side_effect = decode_side_effect
        
        yield
