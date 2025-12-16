# Authentication & Authorization

This guide covers implementing authentication for RAG Lab in production environments.

## Overview

RAG Lab supports multiple authentication strategies:

1. **Development Mode:** No authentication (default for local)
2. **JWT with JWKS:** Enterprise SSO integration (recommended for production)
3. **Service Account Delegation:** GCP service-to-service authentication

## Protected Metadata Fields

Certain metadata fields are **automatically protected** and populated from authenticated user context:

- `uploaded_by`: User email/ID from JWT token
- `organization`: Organization from JWT claims
- `tenant_id`: Multi-tenant identifier

**Protection Rules:**
- Users **cannot** set these fields during upload
- API **overwrites** any client-supplied values
- Values are **extracted from authentication token**

**Example:**
```bash
# Client tries to upload with custom uploaded_by
curl -X POST /upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@doc.pdf" \
  -F 'metadata={"uploaded_by":"fake@example.com"}'  # Ignored!

# API response shows actual user from token
{
  "uploaded_files": [{
    "metadata": {
      "uploaded_by": "alice@company.com"  # From JWT token
    }
  }]
}
```

## JWT with JWKS

Recommended for production deployments with enterprise SSO (Okta, Auth0, Azure AD).

### Configuration

```bash
# .env
AUTH_MODE=jwt
JWKS_URL=https://your-idp.com/.well-known/jwks.json
JWT_AUDIENCE=https://rag-api.your-domain.com
JWT_ISSUER=https://your-idp.com
```

### How It Works

1. Client obtains JWT token from Identity Provider (IdP)
2. Client sends request with `Authorization: Bearer <token>` header
3. RAG Lab validates token signature using JWKS public keys
4. RAG Lab extracts user claims (email, organization, roles)
5. Protected metadata fields are populated from token claims

### Request Example

```bash
# Get token from your IdP
TOKEN=$(curl -X POST https://your-idp.com/oauth/token \
  -d 'client_id=...' \
  -d 'client_secret=...' \
  | jq -r '.access_token')

# Make authenticated request
curl -X POST http://localhost:8080/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@document.pdf" \
  -F 'metadata={"category":"technical"}'
```

### Token Claims

RAG Lab expects these standard JWT claims:

```json
{
  "sub": "user-id-12345",           // Subject (user identifier)
  "email": "alice@company.com",      // User email
  "iss": "https://your-idp.com",     // Issuer (matches JWT_ISSUER)
  "aud": "https://rag-api.your-domain.com",  // Audience (matches JWT_AUDIENCE)
  "exp": 1234567890,                 // Expiration timestamp
  "iat": 1234567800,                 // Issued at timestamp
  "organization": "Engineering",     // Optional: for protected metadata
  "tenant_id": "tenant-123"          // Optional: for multi-tenancy
}
```

### Implementation

```python
# src/auth.py (simplified)
from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
import requests

JWKS_URL = os.getenv("JWKS_URL")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE")
JWT_ISSUER = os.getenv("JWT_ISSUER")

# Fetch public keys from IdP
jwks_client = jwt.PyJWKClient(JWKS_URL)

async def verify_jwt(authorization: str = Header(...)):
    """Verify JWT token and extract user claims."""
    try:
        # Extract token from "Bearer <token>"
        token = authorization.replace("Bearer ", "")
        
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Verify and decode token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER
        )
        
        return payload  # Contains user claims
        
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# Protect endpoints
@app.post("/upload")
async def upload_files(
    files: List[UploadFile],
    metadata: Optional[str] = None,
    user_claims: dict = Depends(verify_jwt)  # Inject user claims
):
    # Parse metadata
    meta = json.loads(metadata) if metadata else {}
    
    # Override protected fields from token
    meta["uploaded_by"] = user_claims.get("email")
    meta["organization"] = user_claims.get("organization")
    meta["tenant_id"] = user_claims.get("tenant_id")
    
    # Process upload with protected metadata
    ...
```

## Service Account Delegation

For service-to-service authentication within GCP.

### Configuration

```bash
# .env
AUTH_MODE=service_account
ALLOWED_SERVICE_ACCOUNTS=service-a@project.iam.gserviceaccount.com,service-b@project.iam.gserviceaccount.com
```

### How It Works

1. Calling service generates ID token with target audience
2. RAG Lab validates token signature and checks service account email
3. Service account email is used for `uploaded_by` metadata

### Request Example

```bash
# Generate ID token (from calling service)
AUDIENCE="https://rag-api-hash-uc.a.run.app"
TOKEN=$(gcloud auth print-identity-token --audiences=$AUDIENCE)

# Make authenticated request
curl -X POST $AUDIENCE/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@document.pdf"
```

### Implementation

```python
# src/auth.py (simplified)
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

ALLOWED_SERVICE_ACCOUNTS = os.getenv("ALLOWED_SERVICE_ACCOUNTS", "").split(",")

async def verify_service_account(authorization: str = Header(...)):
    """Verify GCP ID token and extract service account."""
    try:
        token = authorization.replace("Bearer ", "")
        
        # Verify token with Google
        request = google_requests.Request()
        payload = id_token.verify_oauth2_token(token, request)
        
        # Check service account is allowed
        email = payload.get("email")
        if email not in ALLOWED_SERVICE_ACCOUNTS:
            raise HTTPException(status_code=403, detail="Service account not allowed")
        
        return payload
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
```

## Multi-Tenancy

Implement tenant isolation using protected metadata and filters.

### Upload with Tenant Context

```bash
# Token contains tenant_id claim
curl -X POST /upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@document.pdf"

# Response shows tenant_id from token
{
  "uploaded_files": [{
    "metadata": {
      "tenant_id": "tenant-123",  # From JWT token
      "uploaded_by": "alice@company.com"
    }
  }]
}
```

### Search with Tenant Isolation

```bash
# API automatically adds tenant filter from token
curl -X POST /search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication",
    "metadata_filter": {
      "category": "technical"
    }
  }'

# Backend adds implicit filter:
# {
#   "category": "technical",
#   "tenant_id": "tenant-123"  # From token
# }
```

### Implementation

```python
@app.post("/search")
async def search(
    request: SearchRequest,
    user_claims: dict = Depends(verify_jwt)
):
    # Add tenant filter from token
    tenant_id = user_claims.get("tenant_id")
    if tenant_id:
        metadata_filter = request.metadata_filter or {}
        metadata_filter["tenant_id"] = tenant_id
    
    # Search only tenant's documents
    results = await hybrid_search(
        query=request.query,
        metadata_filter=metadata_filter,
        ...
    )
```

## Disable Authentication (Development)

For local development without auth:

```bash
# .env
AUTH_MODE=none  # or leave unset
```

All endpoints are accessible without tokens. Protected metadata fields are not populated.

## Migration from No-Auth to JWT

1. **Add AUTH_MODE=jwt** to production environment
2. **Configure JWKS_URL, JWT_AUDIENCE, JWT_ISSUER**
3. **Update clients** to send Authorization header
4. **Existing documents** without protected metadata remain accessible
5. **New uploads** get protected metadata from tokens

**Backward Compatibility:**
- Metadata filters with `uploaded_by` only match documents uploaded after auth was enabled
- Use `{"uploaded_by": {"$exists": true}}` to find authenticated uploads

## Testing Authentication

### Unit Tests

```python
# tests/unit/test_auth.py
def test_jwt_validation():
    # Mock JWKS endpoint
    # Create test token
    # Verify extraction of claims
    ...

def test_protected_metadata_override():
    # Client supplies uploaded_by
    # Verify API overwrites with token email
    ...
```

### Integration Tests

```python
# tests/integration/test_auth_flow.py
def test_upload_with_jwt():
    # Generate test JWT
    # Upload document
    # Verify protected metadata from token
    ...
```

## Security Best Practices

1. **Use HTTPS:** Never send tokens over HTTP
2. **Short Token Expiry:** 15-60 minutes for access tokens
3. **Rotate Keys:** IdP should rotate JWKS keys regularly
4. **Validate All Claims:** Check iss, aud, exp, iat
5. **Audit Logs:** Log all authenticated requests
6. **Rate Limiting:** Prevent brute force token attacks
7. **Principle of Least Privilege:** Grant minimal required permissions

## Troubleshooting

### "Invalid token: Signature verification failed"

**Cause:** Token signed with wrong key or JWKS_URL incorrect

**Fix:**
```bash
# Verify JWKS_URL is accessible
curl $JWKS_URL | jq

# Check token issuer matches JWT_ISSUER
echo $TOKEN | cut -d. -f2 | base64 -d | jq .iss
```

### "Token expired"

**Cause:** Token exp claim is in the past

**Fix:** Obtain fresh token from IdP

### "Protected metadata not populated"

**Cause:** Token missing expected claims (email, organization, tenant_id)

**Fix:** Configure IdP to include required claims in tokens
