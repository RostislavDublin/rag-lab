# Multi-stage build for optimized production image
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements-base.txt .

# Production: Install only base dependencies (Vertex AI providers)
# This excludes sentence-transformers + torch (saves ~150MB and ~5 minutes build time)
RUN pip install --no-cache-dir -r requirements-base.txt

# Optional: For on-premise embeddings/reranking, uncomment these lines:
# COPY requirements-optional.txt .
# RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
# RUN pip install --no-cache-dir -r requirements-optional.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/

# Create data directory (no need to copy .gitkeep to production)
RUN mkdir -p data

# .env will be mounted from Secret Manager at runtime (not included in image)

# Cloud Run expects port 8080
ENV PORT=8080

# Create non-root user and set ownership
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Start FastAPI with uvicorn
CMD exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --workers 1
