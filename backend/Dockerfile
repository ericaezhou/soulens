FROM python:3.12-slim

# ffmpeg + curl (for health check) + build tools for native Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (layer-cached unless pyproject.toml/uv.lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Stream logs immediately (required to see Railway logs in real time)
ENV PYTHONUNBUFFERED=1

# Persistent directories — mount a Railway volume at /app/data for profiles + cache
# so expensive AI results survive redeploys. Uploads are ephemeral per-job.
RUN mkdir -p /app/data /app/uploads /app/cache

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
