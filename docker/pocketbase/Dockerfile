FROM alpine:3.19

# Install utilities
RUN apk add --no-cache curl unzip ca-certificates && update-ca-certificates

# Set PocketBase version
ARG POCKETBASE_VERSION=0.40.6
# Construct download URL at runtime

# Create non‑root user
RUN addgroup -S pbgroup && adduser -S pbuser -G pbgroup
# Ensure data directory is writable by the non‑root user
RUN mkdir -p /pb_data && chmod 777 /pb_data && chown pbuser:pbgroup /pb_data

# Set working directory
WORKDIR /app
# Ensure PocketBase data directory is writable for the non‑root user
RUN mkdir -p ./pb_data && chown pbuser:pbgroup ./pb_data && chmod 777 ./pb_data

# Download PocketBase binary
RUN set -eux; \
    URL="https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/pocketbase_${POCKETBASE_VERSION}_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/').zip"; \
    curl -L "$URL" -o pocketbase.zip && \
    unzip pocketbase.zip && \
    chmod +x pocketbase && \
    rm pocketbase.zip

# Copy migration scripts into the container
COPY pb_migrations ./pb_migrations

# Copy entrypoint script
COPY docker/pocketbase/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh && chown pbuser:pbgroup ./entrypoint.sh

# Expose PocketBase HTTP port (default 8090)
EXPOSE 8090

# Use non‑root user
USER pbuser

# Healthcheck – ensure the health endpoint returns 200
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
  CMD wget -qO- http://localhost:8090/api/health || exit 1

# Default command runs PocketBase via entrypoint
ENTRYPOINT ["./entrypoint.sh"]
