#!/bin/bash
set -e
cd "$(dirname "$0")"

# External postgres (simulates Neon)
docker rm -f test-postgres 2>/dev/null || true
docker run -d --name test-postgres --rm \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=notes \
  -p 5433:5432 \
  postgres:16-alpine

echo "Waiting for postgres..."
until docker exec test-postgres pg_isready -U postgres 2>/dev/null; do sleep 1; done

# Build and run app with host network to reach external postgres
docker compose build
docker run --rm -d --name test-app --network=host \
  -e DATABASE_URL="postgres://postgres:postgres@localhost:5433/notes" \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  06-encryption-freshness-app

sleep 2
python3 test_local.py
EXIT_CODE=$?

# Cleanup
docker stop test-app test-postgres 2>/dev/null || true
exit $EXIT_CODE
