#!/bin/sh
set -e

# PocketBase data directory
PB_DATA_DIR="/pb_data"
PB_MIGRATIONS_DIR="./pb_migrations"

# Apply migrations first to ensure all required collections exist
echo "Applying PocketBase migrations..."
./pocketbase migrate up --dir "$PB_DATA_DIR" --migrationsDir "$PB_MIGRATIONS_DIR"

# If superuser credentials are provided, upsert superuser before starting the server
if [ -n "$POCKETBASE_EMAIL" ] && [ -n "$POCKETBASE_PASSWORD" ]; then
  echo "Upserting PocketBase superuser: $POCKETBASE_EMAIL..."
  ./pocketbase superuser upsert "$POCKETBASE_EMAIL" "$POCKETBASE_PASSWORD" --dir "$PB_DATA_DIR"
fi

# CORS origins (env: PB_ALLOWED_ORIGINS, default: http://127.0.0.1:8000,http://localhost:8000)
PB_ALLOWED_ORIGINS=${PB_ALLOWED_ORIGINS:-"http://127.0.0.1:8000,http://localhost:8000"}

echo "Starting PocketBase server..."
exec ./pocketbase serve --http=0.0.0.0:8090 --dir "$PB_DATA_DIR" --origins="$PB_ALLOWED_ORIGINS" "$@"
