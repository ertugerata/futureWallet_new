# FutureWallet PocketBase Dockerfile
# Alpine 3.22 (current LTS as of 2026), PocketBase 0.40.6 with checksum verification

FROM alpine:3.22

# Install utilities
RUN apk add --no-cache curl unzip ca-certificates && update-ca-certificates

# Set PocketBase version
ARG POCKETBASE_VERSION=0.40.6

# Create non-root user
RUN addgroup -S pbgroup && adduser -S pbuser -G pbgroup

# Ensure data directory is writable by the non-root user (chown instead of chmod 777)
RUN mkdir -p /pb_data && chown pbuser:pbgroup /pb_data

# Set working directory
WORKDIR /app

# Download PocketBase binary with checksum verification (using checksums.txt)
RUN set -eux; \
    ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')"; \
    OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; \
    FILE="pocketbase_${POCKETBASE_VERSION}_${OS}_${ARCH}.zip"; \
    URL="https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/${FILE}"; \
    CHECKSUMS_URL="https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/checksums.txt"; \
    curl -fsSL "$URL" -o pocketbase.zip && \
    curl -fsSL "$CHECKSUMS_URL" -o checksums.txt && \
    EXPECTED_SUM=$(grep "${FILE}" checksums.txt | awk '{print $1}') && \
    echo "${EXPECTED_SUM}  pocketbase.zip" | sha256sum -c - && \
    unzip pocketbase.zip && \
    chmod +x pocketbase && \
    rm pocketbase.zip checksums.txt

# Copy migration scripts into the container
COPY pb_migrations ./pb_migrations

# Copy entrypoint script
COPY docker/pocketbase/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh && chown pbuser:pbgroup ./entrypoint.sh

# Expose PocketBase HTTP port (default 8090)
EXPOSE 8090

# Use non-root user
USER pbuser

# Healthcheck – ensure the health endpoint returns 200
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
  CMD wget -qO- http://localhost:8090/api/health || exit 1

# Default command runs PocketBase via entrypoint
# Note: Superuser password is passed via CLI args in entrypoint.sh.
# For production, consider using Docker secrets or a mounted secret file.
ENTRYPOINT ["./entrypoint.sh"]