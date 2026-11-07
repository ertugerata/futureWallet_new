#!/bin/sh
set -e
# Start PocketBase in background
./pocketbase serve --http=0.0.0.0:8090 --dir /pb_data &
PB_PID=$!
# Wait until health endpoint is reachable
until curl -s http://localhost:8090/api/health > /dev/null; do
  echo "Waiting for PocketBase to be ready..."
  sleep 1
done
# Create or update superuser using env vars
if [ -n "$POCKETBASE_EMAIL" ] && [ -n "$POCKETBASE_PASSWORD" ]; then
  ./pocketbase superuser upsert "$POCKETBASE_EMAIL" "$POCKETBASE_PASSWORD"
fi
# Bring PocketBase to foreground
wait $PB_PID
