# FutureWallet - Multi-stage Dockerfile
# Stage 1: builder (Python dependencies)
# Stage 2: runtime (application)

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Build dependencies (for packages with C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Runtime dependencies (curl/wget for healthcheck is optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application code
COPY . .

# Do NOT copy .env — secrets are injected via docker-compose environment
# (see docker-compose.yml environment section)

EXPOSE 8000

# ---------------------------------------------------------------------------
# Non-root user (Prompt 15: "USER app" — root-olmayan kullanıcı)
# ---------------------------------------------------------------------------
RUN useradd -r app && \
    mkdir -p /app/data && \
    chown -R app:app /app
USER app

# ---------------------------------------------------------------------------
# Healthcheck (Prompt 15)
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ---------------------------------------------------------------------------
# Entrypoint: host/port from env vars (Prompt 1: don't bind 0.0.0.0)
# ---------------------------------------------------------------------------
# APP_HOST and APP_PORT are set in docker-compose.yml environment section.
# Defaults: 127.0.0.1:8000 (safe — only localhost until reverse proxy added).
CMD uvicorn api.app:app --host ${APP_HOST:-127.0.0.1} --port ${APP_PORT:-8000}
