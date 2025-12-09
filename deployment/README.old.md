# RAG Lab - Cloud Run Deployment Scripts

This directory contains scripts for deploying to Cloud Run.

## Quick Start

1. **Set your GCP project:**
   ```bash
   export PROJECT_ID="your-project-id"
   gcloud config set project $PROJECT_ID
   ```

2. **Deploy to Cloud Run:**
   ```bash
   ./deploy-cloudrun.sh
   ```

3. **Test the deployment:**
   ```bash
   ./test-deployment.sh
   ```

## Files

- `deploy-cloudrun.sh` - Deploy application to Cloud Run
- `test-deployment.sh` - Test deployed Cloud Run service
- `local-run.sh` - Run locally with Docker (for testing)

## Environment Variables

Cloud Run service will use these environment variables:

- `GCP_PROJECT_ID` - Your GCP project ID
- `GCP_LOCATION` - Vertex AI region (default: us-central1)
- `PORT` - Port for the service (Cloud Run sets this to 8080)

## Cost Estimate

Cloud Run pricing (as of Dec 2024):
- First 2 million requests/month: FREE
- CPU: $0.00002400 per vCPU-second
- Memory: $0.00000250 per GiB-second
- Requests: $0.40 per million

Typical small workload: **$0-5/month**

Scale-to-zero means you pay nothing when idle!
