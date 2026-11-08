#!/bin/sh
set -e

# PocketBase data directory
PB_DATA_DIR="/pb_data"

# If superuser credentials are provided, upsert superuser before starting the server
if [ -n "$POCKETBASE_EMAIL" ] && [ -n "$POCKETBASE_PASSWORD" ]; then
  echo "Upserting PocketBase superuser: $POCKETBASE_EMAIL..."
  ./pocketbase superuser upsert "$POCKETBASE_EMAIL" "$POCKETBASE_PASSWORD" --dir "$PB_DATA_DIR"
fi

echo "Starting PocketBase server..."
exec ./pocketbase serve --http=0.0.0.0:8090 --dir "$PB_DATA_DIR" "$@"
