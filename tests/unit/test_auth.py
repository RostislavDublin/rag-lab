"""
Unit tests for authentication module

Tests vendor-independent JWT token validation using JWKS and whitelist authorization.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi import HTTPException
from src.auth import (
    verify_jwt_token,
    check_authorization,
    get_current_user,
    AuthError,
    ALLOWED_USERS,
)


class TestTokenVerification:
    """Test JWT token verification using JWKS"""
    
    def test_verify_jwt_token_dev_mode(self, monkeypatch):
        """Test dev mode when AUDIENCE is empty"""
        monkeypatch.setenv("AUDIENCE", "")
        
        # Create simple JWT without signature (for dev mode)
        import jwt
        token = jwt.encode(
            {"email": "test@example.com", "sub": "test_user_id"},
            "secret",
            algorithm="HS256"
        )
        
        # Should decode without verification in dev mode
        user_info = verify_jwt_token(token)
        
        assert user_info["email"] == "test@example.com"
        assert user_info["sub"] == "test_user_id"
    
    def test_verify_jwt_token_invalid_format(self, monkeypatch):
        """Test invalid token format"""
        monkeypatch.setenv("AUDIENCE", "")
        
        with pytest.raises(AuthError) as exc_info:
            verify_jwt_token("not_a_jwt_token")
        
        assert "Invalid token format" in str(exc_info.value.detail)
    
    def test_verify_jwt_token_production(self, monkeypatch):
        """Test production mode with JWKS verification"""
        monkeypatch.setenv("AUDIENCE", "test_client_id.apps.googleusercontent.com")
        monkeypatch.setenv("JWKS_URL", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setenv("ISSUER", "https://accounts.google.com")
        
        # Reload auth module to pick up new AUDIENCE
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Create a valid JWT token for testing
        import jwt as pyjwt
        test_token = pyjwt.encode(
            {"email": "user@gmail.com", "sub": "google_user_123", "name": "Test User"},
            "test_secret",
            algorithm="HS256"
        )
        
        # Mock both PyJWKClient and jwt.decode at src.auth level
        with patch("src.auth.PyJWKClient") as mock_jwks_client, \
             patch("src.auth.jwt.decode") as mock_jwt_decode:
            
            # Mock JWKS client and signing key
            mock_signing_key = Mock()
            mock_signing_key.key = "test_public_key"
            mock_client_instance = Mock()
            mock_client_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks_client.return_value = mock_client_instance
            
            # Mock jwt.decode response
            mock_jwt_decode.return_value = {
                "email": "user@gmail.com",
                "sub": "google_user_123",
                "name": "Test User",
            }
            
            user_info = auth.verify_jwt_token(test_token)
            
            assert user_info["email"] == "user@gmail.com"
            assert user_info["sub"] == "google_user_123"
            assert user_info["name"] == "Test User"
            
            # Verify JWKS client was called
            mock_jwks_client.assert_called_once()
            mock_jwt_decode.assert_called_once()
        
        # Restore dev mode
        monkeypatch.setenv("AUDIENCE", "")
        importlib.reload(auth)
    
    def test_verify_jwt_token_invalid_issuer(self, monkeypatch):
        """Test token with invalid issuer"""
        monkeypatch.setenv("AUDIENCE", "test_client_id")
        monkeypatch.setenv("ISSUER", "https://accounts.google.com")
        
        # Reload auth module to pick up AUDIENCE
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Create a valid JWT token
        import jwt as pyjwt
        test_token = pyjwt.encode(
            {"email": "user@example.com", "sub": "fake_123"},
            "test_secret",
            algorithm="HS256"
        )
        
        with patch("src.auth.PyJWKClient") as mock_jwks_client, \
             patch("src.auth.jwt.decode") as mock_jwt_decode:
            
            # Mock JWKS client
            mock_signing_key = Mock()
            mock_signing_key.key = "test_key"
            mock_client_instance = Mock()
            mock_client_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks_client.return_value = mock_client_instance
            
            # Mock jwt.decode raising InvalidTokenError for wrong issuer
            from jwt.exceptions import InvalidTokenError
            mock_jwt_decode.side_effect = InvalidTokenError("Invalid issuer")
            
            with pytest.raises(auth.AuthError) as exc_info:
                auth.verify_jwt_token(test_token)
            
            assert "Invalid token" in str(exc_info.value.detail)
        
        # Restore dev mode
        monkeypatch.setenv("AUDIENCE", "")
        importlib.reload(auth)
    
    def test_verify_jwt_token_expired(self, monkeypatch):
        """Test expired token"""
        monkeypatch.setenv("AUDIENCE", "test_client_id")
        
        # Reload to pick up AUDIENCE
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Create a valid JWT token
        import jwt as pyjwt
        test_token = pyjwt.encode(
            {"email": "user@example.com", "sub": "user_123"},
            "test_secret",
            algorithm="HS256"
        )
        
        with patch("src.auth.PyJWKClient") as mock_jwks_client:
            # Mock JWKS client to raise ExpiredSignatureError when getting signing key
            from jwt.exceptions import ExpiredSignatureError
            mock_client_instance = Mock()
            mock_client_instance.get_signing_key_from_jwt.side_effect = ExpiredSignatureError("Token expired")
            mock_jwks_client.return_value = mock_client_instance
            
            with pytest.raises(auth.AuthError) as exc_info:
                auth.verify_jwt_token(test_token)
            
            assert "expired" in str(exc_info.value.detail).lower()
        
        # Restore dev mode
        monkeypatch.setenv("AUDIENCE", "")
        importlib.reload(auth)


class TestAuthorization:
    """Test whitelist-based authorization"""
    
    def setup_method(self):
        """Reload auth module before each test"""
        import importlib
        from src import auth
        importlib.reload(auth)
    
    def test_check_authorization_allowed_user(self, monkeypatch):
        """Test authorized user from whitelist"""
        monkeypatch.setenv("ALLOWED_USERS", "user1@example.com,user2@example.com")
        
        # Reload ALLOWED_USERS from env
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Should not raise exception
        auth.check_authorization("user1@example.com")
        auth.check_authorization("user2@example.com")
    
    def test_check_authorization_forbidden_user(self, monkeypatch):
        """Test unauthorized user not in whitelist"""
        monkeypatch.setenv("ALLOWED_USERS", "admin@example.com")
        
        import importlib
        from src import auth
        importlib.reload(auth)
        
        with pytest.raises(HTTPException) as exc_info:
            auth.check_authorization("hacker@evil.com")
        
        assert exc_info.value.status_code == 403
        assert "not authorized" in exc_info.value.detail
    
    def test_check_authorization_default_user(self, monkeypatch):
        """Test default allowed user (javaisforever@gmail.com)"""
        monkeypatch.setenv("ALLOWED_USERS", "javaisforever@gmail.com")
        
        # Reload with default env
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Default user should now be allowed
        auth.check_authorization("javaisforever@gmail.com")


class TestGetCurrentUser:
    """Test FastAPI dependency for extracting authenticated user"""
    
    @pytest.mark.asyncio
    async def test_get_current_user_success(self, monkeypatch):
        """Test successful authentication and authorization"""
        monkeypatch.setenv("AUDIENCE", "")
        monkeypatch.setenv("ALLOWED_USERS", "test@example.com")
        
        from src import auth
        auth.ALLOWED_USERS = ["test@example.com"]
        
        # Create mock credentials
        import jwt
        token = jwt.encode(
            {"email": "test@example.com", "sub": "test_123"},
            "secret",
            algorithm="HS256"
        )
        
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        user_email = await get_current_user(credentials)
        
        assert user_email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_current_user_unauthorized(self, monkeypatch):
        """Test unauthorized user (not in whitelist)"""
        monkeypatch.setenv("AUDIENCE", "")
        monkeypatch.setenv("ALLOWED_USERS", "admin@example.com")
        
        from src import auth
        auth.ALLOWED_USERS = ["admin@example.com"]
        
        import jwt
        token = jwt.encode(
            {"email": "hacker@evil.com", "sub": "hacker_123"},
            "secret",
            algorithm="HS256"
        )
        
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)
        
        assert exc_info.value.status_code == 403
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, monkeypatch):
        """Test invalid token format"""
        monkeypatch.setenv("AUDIENCE", "")
        
        import importlib
        from src import auth
        importlib.reload(auth)
        
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")
        
        with pytest.raises(auth.AuthError):
            await auth.get_current_user(credentials)
