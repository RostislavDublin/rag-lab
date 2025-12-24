# Multi-stage build with optimized layer caching
# Base stage is cached unless requirements-base.txt changes
# Cloud Build will reuse cached layers automatically

# Stage 1: Base image with dependencies
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY requirements first (for better layer caching)
COPY requirements-base.txt .

# Install Python dependencies
# This layer is cached and reused until requirements-base.txt changes
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-base.txt

# Stage 2: Production image with application code
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (libmagic for python-magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from base stage
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/

# Create data directory (no need to copy .gitkeep to production)
RUN mkdir -p data

# .env will be mounted from Secret Manager at runtime (not included in image)

# Cloud Run expects port 8080
ENV PORT=8080

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Add /app to PYTHONPATH so Python can find src module
ENV PYTHONPATH=/app

# Start FastAPI with uvicorn using python -m to respect PYTHONPATH
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
