# Multi-Stage Production Dockerfile for PII/PHI Security Microservice
# Optimized for HuggingFace Transformers, PyTorch CPU Inference, and FastAPI

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime dependencies & curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production
ENV SERVICE_PORT=8080
ENV SERVICE_HOST=0.0.0.0

# Create non-root user
RUN useradd -m -u 1001 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Copy application source and fine-tuned RoBERTa model weights
COPY --chown=appuser:appuser api/ /app/api/
COPY --chown=appuser:appuser models/ /app/models/

# Fail the build rather than shipping an image whose weights are a Git LFS pointer.
RUN if head -c 40 /app/models/roberta-pii-synthetic/model.safetensors | grep -q 'git-lfs.github.com'; then \
      echo 'ERROR: models/roberta-pii-synthetic/model.safetensors is a Git LFS pointer, not real weights. Check out the repo with lfs: true / run git lfs pull.' >&2; \
      exit 1; \
    fi

USER root

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/ready || exit 1

# Launch with Gunicorn and Uvicorn workers for production concurrency
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "-b", "0.0.0.0:8080", "--timeout", "120", "--graceful-timeout", "30"]
