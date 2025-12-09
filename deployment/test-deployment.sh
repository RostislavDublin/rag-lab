#!/bin/bash
# Test deployed Cloud Run service

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: PROJECT_ID not set"
    exit 1
fi

SERVICE_NAME="rag-lab-api"
REGION="${REGION:-us-central1}"

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region $REGION \
    --project=$PROJECT_ID \
    --format='value(status.url)')

echo -e "${GREEN}Testing Cloud Run service: $SERVICE_URL${NC}"
echo ""

# Test health endpoint
echo -e "${YELLOW}1. Testing /health endpoint...${NC}"
curl -s "$SERVICE_URL/health" | jq .
echo ""

# Test root endpoint
echo -e "${YELLOW}2. Testing / endpoint...${NC}"
curl -s "$SERVICE_URL/" | jq .
echo ""

# Test embedding endpoint
echo -e "${YELLOW}3. Testing /v1/embed endpoint...${NC}"
curl -s -X POST "$SERVICE_URL/v1/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "What is RAG?"}' | jq '.dimension'
echo ""

echo -e "${GREEN}All tests passed!${NC}"
echo "View API docs: $SERVICE_URL/docs"
