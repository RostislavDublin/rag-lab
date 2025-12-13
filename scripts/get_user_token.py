#!/usr/bin/env python3
"""
OAuth2 flow with refresh token support for RAG Lab API testing.

This script implements OAuth2 authorization code flow with refresh tokens
to minimize user interaction and enable long-running tests.

Features:
- Refresh token persistence: Saves refresh_token to ~/.rag-lab-refresh-token.json
- Automatic token refresh: Silently refreshes id_token when expired (no browser)
- Browser-based auth: Opens browser only on first run or when refresh_token invalid
- Token caching: Reuses valid id_token (saves API calls)

Usage:
    python scripts/get_user_token.py

Flow:
1. Check cache (~/.rag-lab-refresh-token.json) for refresh_token
2. If refresh_token exists and id_token expired → refresh silently
3. If no refresh_token or invalid → run full OAuth flow (browser)
4. Save refresh_token for future use
5. Output id_token to stdout

First run: Opens browser for consent (access_type=offline gets refresh_token)
Subsequent runs: Silent refresh (no user interaction)
"""

import os
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import json
import base64
from pathlib import Path
import time
import jwt
import urllib.request
import urllib.error

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
env_path = project_root / ".env.local"
load_dotenv(env_path)

# OAuth2 configuration
CLIENT_ID = os.getenv("AUDIENCE")  # Same as AUDIENCE in .env.local
CLIENT_SECRET = os.getenv("CLIENT_SECRET")  # OAuth client secret
REDIRECT_URI = "http://localhost:8080/oauth2callback"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPE = "openid email profile"

# .env.local path for token storage
ENV_FILE = project_root / ".env.local"

# Global variable to store the authorization code
auth_code = None
server_should_stop = False


def is_token_valid(id_token: str, min_remaining_seconds: int = 300) -> bool:
    """
    Check if id_token is still valid with minimum time remaining.
    
    Args:
        id_token: JWT token to check
        min_remaining_seconds: Minimum seconds before expiration (default 5 min)
    
    Returns:
        True if token valid and has at least min_remaining_seconds left
    """
    try:
        payload = jwt.decode(id_token, options={"verify_signature": False})
        exp = payload.get("exp", 0)
        now = time.time()
        remaining = exp - now
        return remaining > min_remaining_seconds
    except Exception:
        return False


def load_cached_tokens() -> dict | None:
    """Load cached tokens from .env.local."""
    # Reload .env.local to get latest tokens
    load_dotenv(ENV_FILE, override=True)
    
    id_token = os.getenv("ID_TOKEN")
    refresh_token = os.getenv("REFRESH_TOKEN")
    
    if not id_token and not refresh_token:
        return None
    
    tokens = {}
    if id_token:
        tokens["id_token"] = id_token
    if refresh_token:
        tokens["refresh_token"] = refresh_token
    
    return tokens


def save_tokens(id_token: str, refresh_token: str | None = None):
    """Save tokens to .env.local."""
    # Read current .env.local content
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            lines = f.readlines()
    else:
        lines = []
    
    # Remove old token lines
    lines = [l for l in lines if not l.startswith("ID_TOKEN=") and not l.startswith("REFRESH_TOKEN=")]
    
    # Get existing refresh_token if not provided
    if not refresh_token:
        cached = load_cached_tokens()
        if cached and "refresh_token" in cached:
            refresh_token = cached["refresh_token"]
    
    # Add new token lines at the end
    if not lines or not lines[-1].endswith("\n"):
        lines.append("\n")
    
    lines.append(f"# OAuth tokens (auto-generated, do not edit manually)\n")
    lines.append(f"ID_TOKEN={id_token}\n")
    if refresh_token:
        lines.append(f"REFRESH_TOKEN={refresh_token}\n")
    
    # Write back
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)


def refresh_id_token(refresh_token: str) -> str | None:
    """
    Use refresh_token to get new id_token without user interaction.
    
    Args:
        refresh_token: Long-lived refresh token from initial OAuth flow
    
    Returns:
        New id_token or None if refresh failed
    """
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    try:
        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=urlencode(token_data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        with urllib.request.urlopen(req) as response:
            token_response = json.loads(response.read())
        
        id_token = token_response.get("id_token")
        
        if id_token:
            # Save refreshed token (keep same refresh_token)
            save_tokens(id_token)
            return id_token
        
        return None
        
    except urllib.error.HTTPError as e:
        # Refresh token invalid/expired - need full OAuth flow
        print(f"Refresh token invalid, need re-authorization: {e}", file=sys.stderr)
        return None


class OAuth2CallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth2 callback from Google."""
    
    def do_GET(self):
        global auth_code, server_should_stop
        
        # Parse the callback URL
        query_components = parse_qs(urlparse(self.path).query)
        
        if "code" in query_components:
            auth_code = query_components["code"][0]
            
            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <head><title>Authentication Successful</title></head>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                    <script>window.close();</script>
                </body>
                </html>
            """)
            server_should_stop = True
            
        elif "error" in query_components:
            error = query_components["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <head><title>Authentication Failed</title></head>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {error}</p>
                </body>
                </html>
            """.encode())
            server_should_stop = True
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


def decode_jwt_payload(token):
    """Decode JWT payload without verification (for display only)."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Add padding if needed
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None


def run_full_oauth_flow() -> tuple[str, str | None]:
    """
    Run complete OAuth2 authorization code flow with browser.
    
    Returns:
        Tuple of (id_token, refresh_token)
    """
    global auth_code, server_should_stop
    
    # Reset global state
    auth_code = None
    server_should_stop = False
    
    if not CLIENT_ID:
        print("ERROR: AUDIENCE not set in .env.local", file=sys.stderr)
        sys.exit(1)
    
    if not CLIENT_SECRET:
        print("ERROR: CLIENT_SECRET not set in .env.local", file=sys.stderr)
        sys.exit(1)
    
    # Step 1: Build authorization URL with access_type=offline
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",  # Request refresh_token
        "prompt": "consent"         # Force consent screen (needed for refresh_token)
    }
    auth_url = f"{AUTH_ENDPOINT}?{urlencode(auth_params)}"
    
    print("Opening browser for authorization...", file=sys.stderr)
    
    # Step 2: Start local server for callback
    server = HTTPServer(("localhost", 8080), OAuth2CallbackHandler)
    
    # Step 3: Open browser for user consent
    webbrowser.open(auth_url)
    
    # Step 4: Wait for callback
    while not server_should_stop:
        server.handle_request()
    
    if not auth_code:
        print("ERROR: No authorization code received", file=sys.stderr)
        sys.exit(1)
    
    # Step 5: Exchange code for tokens
    token_data = {
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    try:
        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=urlencode(token_data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        with urllib.request.urlopen(req) as response:
            token_response = json.loads(response.read())
        
        id_token = token_response.get("id_token")
        refresh_token = token_response.get("refresh_token")  # May be None if already authorized
        
        if not id_token:
            print("ERROR: No ID token in response", file=sys.stderr)
            sys.exit(1)
        
        return id_token, refresh_token
        
    except urllib.error.HTTPError as e:
        print(f"ERROR: Token exchange failed: {e}", file=sys.stderr)
        print(e.read().decode(), file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main entry point: Get valid id_token using cache, refresh, or full OAuth flow.
    
    Logic:
    1. Check cache for valid id_token → return it
    2. Check cache for refresh_token → use it to get new id_token
    3. No cache or refresh failed → run full OAuth flow (browser)
    """
    
    # Try to use cached tokens
    cached = load_cached_tokens()
    
    if cached:
        id_token = cached.get("id_token")
        refresh_token = cached.get("refresh_token")
        
        # Check if cached id_token still valid (5+ min remaining)
        if id_token and is_token_valid(id_token, min_remaining_seconds=300):
            print(id_token)  # Output to stdout for pytest
            return
        
        # id_token expired, try to refresh if we have refresh_token
        if refresh_token:
            print("Token expired, refreshing silently...", file=sys.stderr)
            new_id_token = refresh_id_token(refresh_token)
            
            if new_id_token:
                print("Token refreshed successfully", file=sys.stderr)
                print(new_id_token)  # Output to stdout
                return
            
            # Refresh failed, will run full OAuth flow
            print("Refresh failed, running full OAuth flow...", file=sys.stderr)
    
    # No valid cache or refresh failed - run full OAuth flow
    id_token, refresh_token = run_full_oauth_flow()
    
    # Save tokens for future use
    save_tokens(id_token, refresh_token)
    
    if refresh_token:
        print("Authorization successful, refresh_token saved", file=sys.stderr)
    else:
        print("Authorization successful (already had refresh_token)", file=sys.stderr)
    
    print(id_token)  # Output to stdout for pytest


if __name__ == "__main__":
    main()
