#!/usr/bin/env bash
set -Eeuo pipefail

# Migrate data from an old JobFit PostgreSQL dump into the current database.
#
# Usage:
#
#   ./scripts/migrate_from_old_pg.sh --empty-db
#   ./scripts/migrate_from_old_pg.sh --with-jobs
#
# --empty-db
#   The target database must contain zero jobs.
#   Jobs are restored from the dump.
#   LLM-related tables are then merged.
#
# --with-jobs
#   Existing target jobs are preserved.
#   Jobs are NOT restored from the dump.
#   LLM-related tables are merged only for matching jobs.
#
# Expected dump:
#
#   /var/lib/migration/jobfit/incoming/old-jobfit.dump
#
# The dump is created separately by user "archie".
# This script is executed by user "dev".
#
# No sudo is required.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

MIGRATION_ROOT="/var/lib/migration/jobfit"
INCOMING_DIR="$MIGRATION_ROOT/incoming"
PROCESSED_DIR="$MIGRATION_ROOT/processed"

DUMP_FILE="$INCOMING_DIR/old-jobfit.dump"

OLD_CONTAINER="pg-old"
OLD_DATABASE_URL="postgresql://jobfit:jobfit@pg-old:5432/jobfit"

DB_USER="jobfit"
DB_NAME="jobfit"

ROLE="${ROLE:-devops}"

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage:
  $0 --empty-db
  $0 --with-jobs

Modes:
  --empty-db
      Target DB must have zero jobs.
      Restore jobs from the dump and merge old LLM data.

  --with-jobs
      Keep existing target jobs.
      Do not restore jobs from the dump.
      Merge old LLM data for matching jobs.

Environment:
  ROLE=devops

Example:
  ROLE=devops $0 --empty-db
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

log() {
    echo
    echo "==> $*"
}

sql() {
    docker compose exec -T db \
        psql \
            -U "$DB_USER" \
            -d "$DB_NAME" \
            "$@"
}

# ------------------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------------------

MODE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --empty-db)
            [[ -z "$MODE" ]] || die "Choose exactly one mode"
            MODE="empty-db"
            shift
            ;;

        --with-jobs)
            [[ -z "$MODE" ]] || die "Choose exactly one mode"
            MODE="with-jobs"
            shift
            ;;

        -h|--help)
            usage
            exit 0
            ;;

        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$MODE" ]] || {
    usage
    exit 1
}

# ------------------------------------------------------------------------------
# Preconditions
# ------------------------------------------------------------------------------

[[ "$(id -un)" == "dev" ]] ||
    die "This script must be run as user 'dev'"

command -v docker >/dev/null ||
    die "docker not found"

[[ -r "$DUMP_FILE" ]] ||
    die "Dump is not readable: $DUMP_FILE"

log "Migration configuration"

echo "Project: $PROJECT_DIR"
echo "Mode:    $MODE"
echo "Role:    $ROLE"
echo "Dump:    $DUMP_FILE"

# ------------------------------------------------------------------------------
# Start target database
# ------------------------------------------------------------------------------

log "Starting target database"

docker compose up -d db

log "Waiting for target database"

until docker compose exec -T db \
    pg_isready \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        >/dev/null 2>&1
do
    sleep 1
done

echo "Target database is ready."

# ------------------------------------------------------------------------------
# Validate target jobs
# ------------------------------------------------------------------------------

TARGET_JOBS="$(
    sql -tAc "SELECT count(*) FROM jobs;"
)"

TARGET_JOBS="$(xargs <<<"$TARGET_JOBS")"

echo "Target jobs: $TARGET_JOBS"

if [[ "$MODE" == "empty-db" ]]; then
    [[ "$TARGET_JOBS" == "0" ]] || {
        die "--empty-db requires an empty jobs table; found $TARGET_JOBS jobs"
    }
fi

# ------------------------------------------------------------------------------
# Create temporary old PostgreSQL container
# ------------------------------------------------------------------------------

log "Creating temporary old PostgreSQL container"

docker rm -f "$OLD_CONTAINER" >/dev/null 2>&1 || true

DB_CONTAINER_ID="$(docker compose ps -q db)"

[[ -n "$DB_CONTAINER_ID" ]] ||
    die "Could not determine target database container"

COMPOSE_NETWORK="$(
    docker inspect "$DB_CONTAINER_ID" \
        --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}'
)"

[[ -n "$COMPOSE_NETWORK" ]] ||
    die "Could not determine Compose network"

echo "Compose network: $COMPOSE_NETWORK"

docker run -d \
    --name "$OLD_CONTAINER" \
    --network "$COMPOSE_NETWORK" \
    -e POSTGRES_USER=jobfit \
    -e POSTGRES_PASSWORD=jobfit \
    -e POSTGRES_DB=jobfit \
    postgres:16-alpine \
    postgres \
        -c fsync=off \
        -c synchronous_commit=off \
        -c full_page_writes=off \
    >/dev/null

cleanup() {
    log "Removing temporary old PostgreSQL container"
    docker rm -f "$OLD_CONTAINER" >/dev/null 2>&1 || true
}

trap cleanup EXIT

# ------------------------------------------------------------------------------
# Restore dump into temporary PostgreSQL
# ------------------------------------------------------------------------------

log "Waiting for temporary PostgreSQL"

until docker exec "$OLD_CONTAINER" \
    pg_isready \
        -U jobfit \
        -d jobfit \
        >/dev/null 2>&1
do
    sleep 1
done

log "Restoring old database dump"

docker exec -i "$OLD_CONTAINER" \
    pg_restore \
        -U jobfit \
        -d jobfit \
        --no-owner \
        --no-acl \
        < "$DUMP_FILE"

log "Checking old database"

OLD_JOBS="$(
    docker exec "$OLD_CONTAINER" \
        psql \
            -U jobfit \
            -d jobfit \
            -tAc \
            "SELECT count(*) FROM jobs;"
)"

OLD_JOBS="$(xargs <<<"$OLD_JOBS")"

echo "Old database jobs: $OLD_JOBS"

# ------------------------------------------------------------------------------
# Restore jobs when target is empty
# ------------------------------------------------------------------------------

if [[ "$MODE" == "empty-db" ]]; then
    log "Restoring jobs into target database"

    docker exec "$OLD_CONTAINER" \
        pg_dump \
            -U jobfit \
            -d jobfit \
            --data-only \
            --no-owner \
            --no-acl \
            --table=jobs \
    | docker compose exec -T db \
        psql \
            -U "$DB_USER" \
            -d "$DB_NAME"

    log "Checking restored jobs"

    sql -c "
        SELECT role, count(*)
        FROM jobs
        GROUP BY role
        ORDER BY role;
    "
fi

# ------------------------------------------------------------------------------
# Merge LLM-related data
# ------------------------------------------------------------------------------

log "Running merge_from_old_pg.py"

docker compose run --rm \
    -e "OLD_DATABASE_URL=$OLD_DATABASE_URL" \
    app \
    python scripts/merge_from_old_pg.py \
        --role "$ROLE"

# ------------------------------------------------------------------------------
# Final verification
# ------------------------------------------------------------------------------

log "Final verification"

sql -c "
    SELECT
        (SELECT count(*)
         FROM jobs
         WHERE role = '$ROLE') AS jobs,

        (SELECT count(*)
         FROM classifications
         WHERE role = '$ROLE') AS classifications,

        (SELECT count(*)
         FROM known_brands) AS known_brands,

        (SELECT count(*)
         FROM unmatched_industries) AS unmatched_industries;
"

# ------------------------------------------------------------------------------
# Archive dump
# ------------------------------------------------------------------------------

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVED_DUMP="$PROCESSED_DIR/old-jobfit-$TIMESTAMP.dump"

mkdir -p "$PROCESSED_DIR"

if [[ -w "$PROCESSED_DIR" ]]; then
    mv "$DUMP_FILE" "$ARCHIVED_DUMP"
    echo
    echo "Dump archived:"
    echo "  $ARCHIVED_DUMP"
else
    echo
    echo "WARNING: processed directory is not writable."
    echo "Dump remains at:"
    echo "  $DUMP_FILE"
fi

log "Migration completed successfully"
