"""
Authentication module for RAG Lab

Vendor-independent JWT token validation using JWKS (JSON Web Key Set).
Supports any OIDC-compliant provider: Google, Azure AD, Auth0, Okta, etc.

Authorization:
- Whitelist-based: only emails in ALLOWED_USERS env var can access API
- Future: Can extend to role-based access control (RBAC)

Configuration (environment variables):
- JWKS_URL: URL to provider's JWKS endpoint (e.g., https://www.googleapis.com/oauth2/v3/certs)
- ISSUER: Expected token issuer (e.g., https://accounts.google.com)
- AUDIENCE: Expected audience (client ID)
- ALLOWED_USERS: Comma-separated whitelist of emails
"""

import os
import logging
from typing import Optional
from fastapi import HTTPException, Security, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(
    scheme_name="HTTPBearer",
    description="JWT token from OIDC provider (Google, Azure AD, Auth0, etc.)"
)

# Load config from environment
JWKS_URL = os.getenv("JWKS_URL", "https://www.googleapis.com/oauth2/v3/certs")  # Google default
ISSUER = os.getenv("ISSUER", "https://accounts.google.com")  # Google default
AUDIENCE = os.getenv("AUDIENCE", "")  # Client ID
ALLOWED_USERS_STR = os.getenv("ALLOWED_USERS", "javaisforever@gmail.com")
ALLOWED_USERS = [email.strip() for email in ALLOWED_USERS_STR.split(",") if email.strip()]

print(f"Auth configured: {len(ALLOWED_USERS)} allowed users, JWKS={JWKS_URL}")


class AuthError(HTTPException):
    """Custom exception for authentication errors"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_jwt_token(token: str) -> dict:
    """
    Verify JWT token using JWKS (vendor-independent)
    
    Supports any OIDC-compliant provider:
    - Google (https://www.googleapis.com/oauth2/v3/certs)
    - Azure AD (https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys)
    - Auth0 (https://{domain}/.well-known/jwks.json)
    - Okta (https://{domain}/oauth2/default/v1/keys)
    
    Args:
        token: JWT token from Authorization header
    
    Returns:
        dict with user claims: {"email": "user@example.com", "sub": "user_id", ...}
    
    Raises:
        AuthError: If token is invalid, expired, or signature verification fails
    """
    try:
        # Verify token using JWKS
        jwks_client = PyJWKClient(JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        data = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )
        
        return {
            "email": data.get("email"),
            "sub": data.get("sub"),
            "name": data.get("name"),
        }
        
    except ExpiredSignatureError:
        raise AuthError("Token has expired")
    except InvalidTokenError as e:
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
    credentials: HTTPAuthorizationCredentials = Security(security),
    x_end_user_id: Optional[str] = Header(None, alias="X-End-User-ID")
) -> str:
    """
    FastAPI dependency: Extract and validate user from JWT token or X-End-User-ID header
    
    Supports two authentication scenarios:
    1. User-to-Service: User's JWT token contains email (standard flow)
    2. Service-to-Service: Service Account JWT + X-End-User-ID header
       - Token must be valid (service account authenticated)
       - X-End-User-ID header contains actual end user email
       - End user must still be in ALLOWED_USERS whitelist
    
    Usage:
        @app.get("/protected")
        async def protected_route(user_email: str = Depends(get_current_user)):
            return {"user": user_email}
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        x_end_user_id: Optional header for service-to-service delegation
    
    Returns:
        User email (verified and authorized)
    
    Raises:
        HTTPException: 401 if token invalid, 403 if user not authorized
    """
    token = credentials.credentials
    
    # Verify token using JWKS
    user_info = verify_jwt_token(token)
    
    # Determine effective user:
    # - If X-End-User-ID header present: use it (service-to-service flow)
    # - Otherwise: use email from token (user-to-service flow)
    if x_end_user_id:
        email = x_end_user_id
        logger.info(f"Service-to-service request: SA token with end user={email}")
    else:
        email = user_info["email"]
        logger.info(f"User-to-service request: user={email}")
    
    # Check authorization (whitelist) for the effective user
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
