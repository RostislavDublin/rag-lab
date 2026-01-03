# Single-stage build
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements-base.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-base.txt

# Copy application code
COPY src/ ./src/

# Create data directory (no need to copy .gitkeep to production)
RUN mkdir -p data

# .env will be mounted from Secret Manager at runtime (not included in image)

# Cloud Run expects port 8080
ENV PORT=8080

# Add /app to PYTHONPATH so Python can find src module (MUST be before USER switch)
ENV PYTHONPATH=/app

# ENV_FILE path for Cloud Run secret mounting (can be overridden at runtime)
ENV ENV_FILE=/config/.env

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Ensure working directory is /app for the user
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Start FastAPI with uvicorn
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
