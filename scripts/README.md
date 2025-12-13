# Authentication Scripts

## Overview

RAG Lab supports two authentication scenarios:

1. **User-to-Service**: Real user → API (user JWT token)
2. **Service-to-Service**: Service Account → API on behalf of user (SA token + `X-End-User-ID` header)

## Getting User JWT Token

### Refresh Token Flow (Recommended)

The authentication system uses OAuth2 refresh tokens to minimize user interaction:

**First Run** (one-time setup):
```bash
python scripts/get_user_token.py
```
- Opens browser for Google OAuth consent
- Gets **refresh_token** (long-lived, saved to `~/.rag-lab-refresh-token.json`)
- Gets **id_token** (JWT, valid 1 hour)
- Returns id_token

**Subsequent Runs** (automatic, no browser):
```bash
python scripts/get_user_token.py
```
- Checks cached id_token (valid for 5+ minutes?) → Returns it
- Cached token expired? → Silently refreshes using refresh_token (no browser)
- Refresh_token invalid? → Opens browser for re-authorization

### Benefits

✅ **One-time authorization** - Browser opens only once (or when refresh_token revoked)  
✅ **Automatic refresh** - Tokens refresh silently when expired  
✅ **Long-running tests** - Integration tests work seamlessly for hours  
✅ **Secure** - refresh_token stored with 0600 permissions in `~/.rag-lab-refresh-token.json`

### Token Revocation

User can revoke access at any time:
- Google Account → Security → Third-party apps → "RAG Lab Local Testing" → Remove access
- Next test run will re-open browser for fresh authorization

### Setup (First Time)

1. **Add OAuth credentials to `.env.local`**:
   ```bash
   AUDIENCE=<your-client-id>.apps.googleusercontent.com
   CLIENT_SECRET=<your-client-secret>
   ```

2. **Configure OAuth Consent Screen**:
   - Go to: https://console.cloud.google.com/apis/credentials/consent?project=myai-475419
   - Add test user: `javaisforever@gmail.com`
   - Add authorized redirect URI: `http://localhost:8080/oauth2callback`

### Get Token

### Use Token

**Manual Testing with curl**:
```bash
# Get fresh token (uses cache or refreshes automatically)
export TOKEN=$(python scripts/get_user_token.py)

curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8080/v1/documents
```

**Automated Testing (pytest)**:

Tests use `TokenManager` which handles token refresh automatically:

```python
from tests.auth_manager import get_token_manager

# Option 1: Get headers (simple, but won't auto-refresh on 401)
tm = get_token_manager()
headers = tm.get_headers()
response = requests.get(f"{API_BASE}/v1/documents", headers=headers)

# Option 2: Use built-in retry (recommended for long tests)
response = tm.get(f"{API_BASE}/v1/documents", timeout=30)
# Automatically retries on 401 with fresh token

# Option 3: POST with files
response = tm.post(
    f"{API_BASE}/v1/documents/upload",
    files={"file": ("doc.pdf", file_content, "application/pdf")},
    timeout=60
)
```

**Swagger UI**:
1. Get token: `python scripts/get_user_token.py`
2. Open: http://localhost:8080/docs
3. Click "Authorize"
4. Paste token (without "Bearer ")
5. Test endpoints

Note: Swagger tokens expire after 1 hour - refresh manually if needed.

## Service-to-Service Authentication

For service accounts acting on behalf of end users:

### Setup

1. **Get Service Account Token**:
   ```bash
   # Activate service account
   gcloud auth activate-service-account --key-file=service-account-key.json
   
   # Get SA token
   SA_TOKEN=$(gcloud auth print-identity-token --audiences=$AUDIENCE)
   ```

2. **Make Request with X-End-User-ID Header**:
   ```bash
   curl -H "Authorization: Bearer $SA_TOKEN" \
        -H "X-End-User-ID: javaisforever@gmail.com" \
        http://localhost:8080/v1/documents
   ```

### How It Works

1. **Token Validation**: API validates SA token via JWKS
2. **User Identification**: API extracts end user from `X-End-User-ID` header
3. **Authorization Check**: API checks if end user is in `ALLOWED_USERS` whitelist
4. **Data Attribution**: Created data is attributed to end user (not SA)

### Example: Upload Document

```bash
SA_TOKEN=$(gcloud auth print-identity-token --audiences=$AUDIENCE)

curl -X POST http://localhost:8080/v1/documents/upload \
  -H "Authorization: Bearer $SA_TOKEN" \
  -H "X-End-User-ID: javaisforever@gmail.com" \
  -F "file=@document.pdf"
```

Result: Document metadata will have `uploaded_by: javaisforever@gmail.com` (not SA email)

## Authentication Flow Comparison

| Scenario | Token | X-End-User-ID | Effective User |
|----------|-------|---------------|----------------|
| **User-to-Service** | User JWT | (not set) | Email from JWT token |
| **Service-to-Service** | SA JWT | `user@example.com` | Email from header |

## Security Notes

1. **X-End-User-ID Validation**:
   - Header is only accepted if JWT token is valid
   - End user must still be in `ALLOWED_USERS` whitelist
   - Service account cannot impersonate arbitrary users

2. **Whitelist Enforcement**:
   - Both user from token and user from header are checked
   - Unauthorized users get `403 Forbidden`

3. **Audit Trail**:
   - All requests logged with effective user
   - Service-to-service requests logged separately

## Troubleshooting

### "ERROR: Invalid account type for --audiences"

This error occurs when using `gcloud auth print-identity-token --audiences` with user account.

**Solutions**:
1. Use `scripts/get_user_token.py` for user JWT tokens (OAuth flow)
2. Use service account for testing:
   ```bash
   gcloud auth activate-service-account --key-file=service-account-key.json
   gcloud auth print-identity-token --audiences=$AUDIENCE
   ```

### "User not authorized"

User email not in `ALLOWED_USERS` whitelist.

**Solution**: Add to `.env.local`:
```bash
ALLOWED_USERS=javaisforever@gmail.com,other@example.com
```

### "Token expired"

JWT tokens expire in 1 hour.

**Solution**: Get fresh token:
```bash
python scripts/get_user_token.py
```
