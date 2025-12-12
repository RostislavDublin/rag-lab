"""
Authentication module for RAG Lab

Provides JWT token validation using Google Identity Platform.
Supports OAuth2 Bearer tokens with Google-signed JWTs.

Authorization:
- Whitelist-based: only emails in ALLOWED_USERS env var can access API
- Future: Can extend to role-based access control (RBAC)
"""

import os
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.auth.transport import requests
from google.oauth2 import id_token
import jwt

# Security scheme for Swagger UI
security = HTTPBearer(
    scheme_name="Google OAuth2",
    description="Google ID Token (OAuth2). Get from Google Sign-In or gcloud auth print-identity-token"
)

# Load config from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
ALLOWED_USERS_STR = os.getenv("ALLOWED_USERS", "javaisforever@gmail.com")
ALLOWED_USERS = [email.strip() for email in ALLOWED_USERS_STR.split(",") if email.strip()]

print(f"Auth configured: {len(ALLOWED_USERS)} allowed users")


class AuthError(HTTPException):
    """Custom exception for authentication errors"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_google_token(token: str) -> dict:
    """
    Verify Google ID token and return user info
    
    Args:
        token: Google ID token (JWT)
    
    Returns:
        dict with user info: {"email": "user@example.com", "sub": "google_user_id"}
    
    Raises:
        AuthError: If token is invalid or expired
    """
    try:
        # For development: if GOOGLE_CLIENT_ID is empty, allow any token for testing
        # REMOVE THIS IN PRODUCTION - security risk!
        if not GOOGLE_CLIENT_ID:
            print("WARNING: GOOGLE_CLIENT_ID not set - using insecure dev mode")
            # Decode without verification (DEV ONLY)
            try:
                unverified = jwt.decode(token, options={"verify_signature": False})
                return {
                    "email": unverified.get("email", "dev@localhost"),
                    "sub": unverified.get("sub", "dev_user"),
                }
            except Exception as e:
                raise AuthError(f"Invalid token format: {str(e)}")
        
        # Production: verify token with Google
        request = requests.Request()
        id_info = id_token.verify_oauth2_token(
            token, 
            request, 
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10  # Allow 10s clock skew
        )
        
        # Validate issuer
        if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
            raise AuthError("Invalid token issuer")
        
        return {
            "email": id_info.get("email"),
            "sub": id_info.get("sub"),
            "name": id_info.get("name"),
        }
        
    except ValueError as e:
        # Token verification failed
        raise AuthError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise AuthError(f"Token verification failed: {str(e)}")


def check_authorization(email: str) -> None:
    """
    Check if user email is in whitelist
    
    Args:
        email: User email from verified token
    
    Raises:
        HTTPException: 403 if user not authorized
    """
    if email not in ALLOWED_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User {email} is not authorized to access this API. Contact admin to be added to whitelist."
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """
    FastAPI dependency: Extract and validate user from JWT token
    
    Usage:
        @app.get("/protected")
        async def protected_route(user_email: str = Depends(get_current_user)):
            return {"user": user_email}
    
    Args:
        credentials: HTTP Bearer token from Authorization header
    
    Returns:
        User email (verified and authorized)
    
    Raises:
        HTTPException: 401 if token invalid, 403 if user not authorized
    """
    token = credentials.credentials
    
    # Verify token with Google
    user_info = verify_google_token(token)
    email = user_info["email"]
    
    # Check authorization (whitelist)
    check_authorization(email)
    
    return email


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[str]:
    """
    Optional authentication - returns None if no token provided
    
    Useful for endpoints that work both with/without auth
    """
    if not credentials:
        return None
    
    return await get_current_user(credentials)
