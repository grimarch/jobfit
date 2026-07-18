#!/bin/sh
set -e

alembic upgrade head

# Auto-migrate SQLite data on first boot; sentinel prevents re-running
DATA_DIR="${JOBFIT_DATA_DIR:-/secrets/jobfit/data}"
if [ -f "${DATA_DIR}/jobfit.db" ] && [ ! -f "${DATA_DIR}/.pg_migrated" ]; then
    python scripts/migrate_postgres.py && touch "${DATA_DIR}/.pg_migrated"
fi

# Allow one-off CLI commands: docker compose run --rm app jobfit fetch all
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

python -m jobfit.startup || exit 1

exec uvicorn jobfit.app:app --host 0.0.0.0 --port "${APP_HOST_PORT:-8888}"
