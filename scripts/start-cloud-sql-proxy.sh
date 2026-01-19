#!/bin/bash
# Start Cloud SQL Auth Proxy for local development
# This allows local tests to connect to production Cloud SQL database

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Cloud SQL Auth Proxy${NC}"

# Check if proxy is already running
if lsof -Pi :5432 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Port 5432 is already in use. Cloud SQL Proxy may already be running.${NC}"
    echo "To stop it: lsof -ti:5432 | xargs kill"
    exit 1
fi

# Get Cloud SQL instance connection name from secret
echo "Fetching Cloud SQL connection details..."
CONNECTION_NAME=$(gcloud secrets versions access latest \
    --secret=raglab-config \
    --configuration=raglab | grep CLOUD_SQL_CONNECTION_NAME | cut -d= -f2)

if [ -z "$CONNECTION_NAME" ]; then
    echo -e "${RED}ERROR: CLOUD_SQL_CONNECTION_NAME not found in raglab-config secret${NC}"
    echo "Looking for DATABASE_URL instead..."
    
    # Fallback: extract from DATABASE_URL
    DATABASE_URL=$(gcloud secrets versions access latest \
        --secret=raglab-config \
        --configuration=raglab | grep DATABASE_URL | cut -d= -f2-)
    
    if [[ $DATABASE_URL == *"cloudsql"* ]]; then
        # Extract connection name from Cloud SQL socket path
        CONNECTION_NAME=$(echo $DATABASE_URL | grep -oP '/cloudsql/\K[^/]+' || true)
    fi
    
    if [ -z "$CONNECTION_NAME" ]; then
        echo -e "${RED}ERROR: Could not determine Cloud SQL connection name${NC}"
        echo "Please check your raglab-config secret contains either:"
        echo "  - CLOUD_SQL_CONNECTION_NAME=PROJECT:REGION:INSTANCE"
        echo "  - DATABASE_URL with /cloudsql/ path"
        exit 1
    fi
fi

echo -e "${GREEN}Cloud SQL instance: ${CONNECTION_NAME}${NC}"

# Check if cloud-sql-proxy is installed
if ! command -v cloud-sql-proxy &> /dev/null; then
    echo -e "${RED}ERROR: cloud-sql-proxy not installed${NC}"
    echo "Install with: brew install cloud-sql-proxy"
    echo "Or download from: https://cloud.google.com/sql/docs/postgres/sql-proxy"
    exit 1
fi

echo "Starting proxy on localhost:5432..."
echo -e "${YELLOW}Keep this terminal open while running tests${NC}"
echo ""

# Start proxy
cloud-sql-proxy \
    --address 0.0.0.0 \
    --port 5432 \
    $CONNECTION_NAME

# Note: This is a blocking command. Press Ctrl+C to stop.
