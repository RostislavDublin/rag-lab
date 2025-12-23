#!/bin/bash
# Watch Cloud Build progress in real-time

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.deploy"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

PROJECT_ID="${GCP_PROJECT_ID:-myai-475419}"
REGION="${GCP_REGION:-us-central1}"

BUILD_ID="$1"

if [ -z "$BUILD_ID" ]; then
    echo "Usage: $0 <build-id>"
    echo "Getting latest build..."
    BUILD_ID=$(gcloud builds list --region="$REGION" --limit=1 --project="$PROJECT_ID" --format="value(id)")
    if [ -z "$BUILD_ID" ]; then
        echo "No builds found"
        exit 1
    fi
    echo "Watching build: $BUILD_ID"
fi

LAST_STATUS=""
DOTS=0

while true; do
    STATUS=$(gcloud builds describe "$BUILD_ID" --region="$REGION" --project="$PROJECT_ID" --format="value(status)" 2>/dev/null)
    
    if [ -z "$STATUS" ]; then
        echo "Build not found or error getting status"
        exit 1
    fi
    
    # Если статус изменился - выводим
    if [ "$STATUS" != "$LAST_STATUS" ]; then
        echo ""
        echo "[$(date +%H:%M:%S)] Status: $STATUS"
        LAST_STATUS="$STATUS"
        DOTS=0
    else
        # Иначе просто точки для прогресса
        echo -n "."
        DOTS=$((DOTS + 1))
        if [ $DOTS -ge 60 ]; then
            echo ""
            DOTS=0
        fi
    fi
    
    # Если завершился - показываем результат и выходим
    case "$STATUS" in
        SUCCESS)
            echo ""
            echo "✓ BUILD SUCCESSFUL"
            gcloud builds describe "$BUILD_ID" --region="$REGION" --project="$PROJECT_ID" --format="value(results.buildStepImages)" | head -3
            echo ""
            echo "Service URL:"
            gcloud run services describe raglab --region=us-central1 --project="$PROJECT_ID" --format="value(status.url)" 2>/dev/null
            exit 0
            ;;
        FAILURE|TIMEOUT|CANCELLED)
            echo ""
            echo "✗ BUILD FAILED: $STATUS"
            echo ""
            echo "Last 30 log lines:"
            gcloud logging read "resource.type=build AND resource.labels.build_id=\"$BUILD_ID\"" \
                --project="$PROJECT_ID" --limit=30 --format="value(textPayload)" --freshness=1h 2>&1 | tail -30
            exit 1
            ;;
    esac
    
    sleep 5
done
