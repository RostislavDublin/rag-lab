#!/bin/bash
# Run RAG Lab locally with Docker (for testing before Cloud Run deployment)

set -e

echo "Building Docker image locally..."
docker build -t rag-lab-api:local ..

echo ""
echo "Starting container on http://localhost:8080"
echo "Press Ctrl+C to stop"
echo ""

docker run -it --rm \
    -p 8080:8080 \
    -e GCP_PROJECT_ID="${PROJECT_ID:-your-project-id}" \
    -e GCP_LOCATION="${REGION:-us-central1}" \
    rag-lab-api:local
