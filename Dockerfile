# Framework Orchestrator Docker Image
# Multi-stage build for minimal production image

# ========================================
# Stage 1: Builder
# ========================================
FROM python:3.14-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

# ========================================
# Stage 2: Production
# ========================================
FROM python:3.14-slim as production

# Labels
LABEL maintainer="Joseph Ibrahim"
LABEL description="Framework Orchestrator - USD Composition Semantics for AI Agent Orchestration"
LABEL version="3.1.0"

# Create non-root user
RUN groupadd -r orchestrator && useradd -r -g orchestrator orchestrator

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --from=builder /build/*.py ./
COPY --from=builder /build/examples ./examples/
COPY --from=builder /build/docs ./docs/

# Create directories for runtime
RUN mkdir -p /app/workspace/domains \
             /app/workspace/frameworks \
             /app/workspace/results \
             /app/workspace/checkpoints \
    && chown -R orchestrator:orchestrator /app

# Switch to non-root user
USER orchestrator

# Environment variables with defaults
ENV FO_WORKSPACE=/app/workspace \
    FO_DOMAINS=/app/workspace/domains \
    FO_LOG_LEVEL=INFO \
    FO_LOG_FORMAT=json \
    FO_METRICS_ENABLED=true \
    FO_TRACING_ENABLED=true \
    FO_ENABLE_HEALTH_CHECK=true \
    PYTHONUNBUFFERED=1

# Expose HTTP port for health/metrics
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/live')" || exit 1

# Default command: run HTTP server
CMD ["python", "-m", "http_server", "--port", "8080"]
