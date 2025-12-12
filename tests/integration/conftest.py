"""Shared fixtures for integration tests

Integration tests use REAL external services:
- Vertex AI for embeddings (via google-genai SDK)
- PostgreSQL for vector storage
- GCS for document storage
- Running FastAPI server for HTTP API tests

NO MOCKS - these tests verify actual integration with cloud services.

IMPORTANT: Integration tests FAIL LOUDLY if not configured.
They should NOT be silently skipped - if they fail, something is broken!

To run integration tests:
    export GCP_PROJECT_ID=your-project-id
    gcloud auth application-default login
    pytest tests/integration/

To skip integration tests explicitly:
    pytest tests/unit/                    # Only unit tests
    pytest --ignore=tests/integration/    # Exclude integration dir
    pytest -m 'not integration'           # If marked with @pytest.mark.integration

Requirements:
- GCP_PROJECT_ID environment variable (REQUIRED)
- GCP_LOCATION environment variable (optional, defaults to us-central1)
- GCP credentials configured (gcloud auth or service account key)
- Vertex AI API enabled in project
- Network access to GCP services
"""

import pytest
import os
from pathlib import Path
from google import genai
import vertexai
from dotenv import load_dotenv

# Load .env.local for integration tests (same as main.py does)
env_local = Path(__file__).parent.parent.parent / ".env.local"
if env_local.exists():
    load_dotenv(env_local, override=True)


@pytest.fixture(scope="session")
def genai_client():
    """
    Create real Google Gen AI client for integration tests.
    
    Shared across all integration tests in the session.
    Uses real Vertex AI API - requires credentials.
    
    FAILS LOUDLY if not configured - integration tests should not be silently skipped!
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    
    if not project_id:
        pytest.fail(
            "\n\n"
            "❌ GCP_PROJECT_ID not set! Integration tests require real Vertex AI connection.\n"
            "\n"
            "Options:\n"
            "1. Set GCP_PROJECT_ID environment variable and configure credentials:\n"
            "   export GCP_PROJECT_ID=your-project-id\n"
            "   gcloud auth application-default login\n"
            "\n"
            "2. Skip integration tests explicitly:\n"
            "   pytest tests/unit/              # Run only unit tests\n"
            "   pytest -m 'not integration'     # Skip integration marker\n"
            "   pytest --ignore=tests/integration/  # Ignore integration directory\n"
            "\n"
            "Integration tests are NOT optional - they verify real cloud service integration.\n"
            "If they fail, it means something is broken in production!\n"
        )
    
    # Initialize Vertex AI
    vertexai.init(project=project_id, location=location)
    
    # Create real genai client (not mock!)
    client = genai.Client(vertexai=True, project=project_id, location=location)
    
    print(f"\n✓ Created real Vertex AI client (project={project_id}, location={location})")
    
    return client
