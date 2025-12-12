"""
Unit tests for authentication module

Tests JWT token validation, Google Identity verification, and whitelist authorization.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from src.auth import (
    verify_google_token,
    check_authorization,
    get_current_user,
    AuthError,
    ALLOWED_USERS,
)


class TestTokenVerification:
    """Test Google ID token verification"""
    
    def test_verify_google_token_dev_mode(self, monkeypatch):
        """Test dev mode when GOOGLE_CLIENT_ID is empty"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        
        # Create simple JWT without signature (for dev mode)
        import jwt
        token = jwt.encode(
            {"email": "test@example.com", "sub": "test_user_id"},
            "secret",
            algorithm="HS256"
        )
        
        # Should decode without verification in dev mode
        user_info = verify_google_token(token)
        
        assert user_info["email"] == "test@example.com"
        assert user_info["sub"] == "test_user_id"
    
    def test_verify_google_token_invalid_format(self, monkeypatch):
        """Test invalid token format"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        
        with pytest.raises(AuthError) as exc_info:
            verify_google_token("not_a_jwt_token")
        
        assert "Invalid token format" in str(exc_info.value.detail)
    
    @patch("src.auth.id_token.verify_oauth2_token")
    def test_verify_google_token_production(self, mock_verify, monkeypatch):
        """Test production mode with Google verification"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id.apps.googleusercontent.com")
        
        # Reload auth module to pick up new GOOGLE_CLIENT_ID
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Mock Google's verification response
        mock_verify.return_value = {
            "email": "user@gmail.com",
            "sub": "google_user_123",
            "name": "Test User",
            "iss": "accounts.google.com",
        }
        
        user_info = auth.verify_google_token("valid_google_token")
        
        assert user_info["email"] == "user@gmail.com"
        assert user_info["sub"] == "google_user_123"
        assert user_info["name"] == "Test User"
        
        # Verify Google verification was called
        mock_verify.assert_called_once()
        
        # Restore dev mode
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        importlib.reload(auth)
    
    @patch("src.auth.id_token.verify_oauth2_token")
    def test_verify_google_token_invalid_issuer(self, mock_verify, monkeypatch):
        """Test token from wrong issuer"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        
        # Reload auth module to pick up GOOGLE_CLIENT_ID
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Mock token from non-Google issuer
        mock_verify.return_value = {
            "email": "user@example.com",
            "sub": "fake_123",
            "iss": "evil.com",  # Wrong issuer
        }
        
        with pytest.raises(auth.AuthError) as exc_info:
            auth.verify_google_token("fake_token")
        
        assert "Invalid token issuer" in str(exc_info.value.detail)
        
        # Restore dev mode
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        importlib.reload(auth)
    
    @patch("src.auth.id_token.verify_oauth2_token")
    def test_verify_google_token_expired(self, mock_verify, monkeypatch):
        """Test expired token"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        
        # Reload to pick up GOOGLE_CLIENT_ID
        import importlib
        from src import auth
        importlib.reload(auth)
        
        # Mock Google raising ValueError for expired token
        mock_verify.side_effect = ValueError("Token expired")
        
        with pytest.raises(auth.AuthError) as exc_info:
            auth.verify_google_token("fake_expired_token")
        
        assert "Invalid token" in str(exc_info.value.detail)
        
        # Restore dev mode
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
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
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
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
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
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
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        
        import importlib
        from src import auth
        importlib.reload(auth)
        
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")
        
        with pytest.raises(auth.AuthError):
            await auth.get_current_user(credentials)
