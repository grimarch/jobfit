#!/usr/bin/env bash
# Backup jobfit PostgreSQL (and optional data/ artifacts) via Docker Compose.
#
# Usage (from project root):
#   ./scripts/backup.sh              # pg_dump only
#   ./scripts/backup.sh --data       # pg_dump + data/devops tarball
#   ./scripts/backup.sh --keep-days 7
#
# Requires: docker compose, db service running (docker compose up -d db).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP_DAYS=14
INCLUDE_DATA=0
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \?//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data) INCLUDE_DATA=1; shift ;;
        --keep-days) KEEP_DAYS="${2:?missing value for --keep-days}"; shift 2 ;;
        -h|--help) usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

if ! docker compose ps --status running db 2>/dev/null | grep -q db; then
    echo "error: db service is not running — start with: docker compose up -d db" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

PG_USER="${POSTGRES_USER:-jobfit}"
PG_DB="${POSTGRES_DB:-jobfit}"
DUMP_PATH="$BACKUP_DIR/jobfit-${TIMESTAMP}.dump"

echo "Backing up PostgreSQL → $DUMP_PATH"
docker compose exec -T db pg_dump -U "$PG_USER" -d "$PG_DB" -Fc > "$DUMP_PATH"

DUMP_SIZE="$(du -h "$DUMP_PATH" | cut -f1)"
echo "  pg_dump: $DUMP_SIZE"

if [[ "$INCLUDE_DATA" -eq 1 ]]; then
    DATA_PATH="$BACKUP_DIR/jobfit-data-${TIMESTAMP}.tar.gz"
    echo "Backing up data/devops → $DATA_PATH"
    tar -czf "$DATA_PATH" -C "$ROOT/data" devops 2>/dev/null || {
        echo "  warning: data/devops not found, skipping" >&2
        rm -f "$DATA_PATH"
    }
    if [[ -f "$DATA_PATH" ]]; then
        echo "  data: $(du -h "$DATA_PATH" | cut -f1)"
    fi
fi

if [[ "$KEEP_DAYS" -gt 0 ]]; then
    DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'jobfit-*.dump' -o -name 'jobfit-data-*.tar.gz' \) -mtime +"$KEEP_DAYS" -print -delete | wc -l)"
    if [[ "$DELETED" -gt 0 ]]; then
        echo "Pruned $DELETED backup file(s) older than ${KEEP_DAYS} days"
    fi
fi

echo "Done."
