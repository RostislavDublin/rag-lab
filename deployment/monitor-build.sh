#!/bin/bash
# Monitor latest Cloud Build deployment in real-time

set -e

PROJECT_ID="myai-475419"
REGION="us-central1"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Cloud Build Deployment Monitor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check for ongoing builds
echo "Checking for active builds..."
BUILD_ID=$(gcloud builds list --limit=1 --ongoing --project=$PROJECT_ID --format="value(id)" 2>/dev/null || echo "")

if [ -n "$BUILD_ID" ]; then
    echo "✓ Active build found: $BUILD_ID"
    echo ""
    echo "Streaming logs (Ctrl+C to stop)..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    gcloud builds log $BUILD_ID --stream --project=$PROJECT_ID
    echo ""
    
    # Check final status
    STATUS=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(status)")
    if [ "$STATUS" = "SUCCESS" ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✓ BUILD SUCCESSFUL"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Get service URL
        SERVICE_URL=$(gcloud run services describe raglab --region=$REGION --project=$PROJECT_ID --format="value(status.url)" 2>/dev/null || echo "")
        if [ -n "$SERVICE_URL" ]; then
            echo ""
            echo "Service URL: $SERVICE_URL"
            echo "Health check: $SERVICE_URL/health"
            echo ""
            echo "Testing endpoint..."
            if curl -sf "$SERVICE_URL/health" > /dev/null 2>&1; then
                echo "✓ Service is healthy!"
            else
                echo "⚠ Service not responding (may be cold starting, try again in 30s)"
            fi
        fi
    else
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✗ BUILD FAILED: $STATUS"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
    
    exit 0
fi

# No ongoing builds, check latest
echo "No active builds. Checking latest build..."
BUILD_ID=$(gcloud builds list --limit=1 --project=$PROJECT_ID --format="value(id)" 2>/dev/null || echo "")

if [ -z "$BUILD_ID" ]; then
    echo "✗ No builds found"
    echo ""
    echo "Possible reasons:"
    echo "  1. Webhook hasn't triggered yet (wait 30-60 seconds)"
    echo "  2. GitHub repository not connected"
    echo "  3. Trigger not configured"
    echo ""
    echo "To manually trigger:"
    echo "  gcloud builds triggers run deploy-production --region=$REGION --project=$PROJECT_ID --branch=deploy/production"
    exit 1
fi

# Show latest build status
STATUS=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(status)")
CREATE_TIME=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(createTime)")
BRANCH=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(source.repoSource.branchName)" 2>/dev/null || echo "N/A")

echo ""
echo "Latest build: $BUILD_ID"
echo "Status: $STATUS"
echo "Branch: $BRANCH"
echo "Created: $CREATE_TIME"
echo ""

if [ "$STATUS" = "SUCCESS" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✓ BUILD SUCCESSFUL"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
elif [ "$STATUS" = "FAILURE" ] || [ "$STATUS" = "TIMEOUT" ] || [ "$STATUS" = "CANCELLED" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✗ BUILD FAILED: $STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Last 50 lines of logs:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    gcloud builds log $BUILD_ID --project=$PROJECT_ID 2>/dev/null | tail -50 || echo "Failed to retrieve logs"
else
    echo "Build in progress or unknown status: $STATUS"
fi

echo ""
echo "View full logs:"
echo "  gcloud builds log $BUILD_ID --project=$PROJECT_ID"
echo ""
echo "Or in console:"
echo "  https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PROJECT_ID"
