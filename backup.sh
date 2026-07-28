#!/usr/bin/env sh

set -eu

container_id="$(docker compose ps --quiet open-quiz-backend)"
if [ -z "$container_id" ]; then
    echo "The backend container must be running before a backup can be created." >&2
    exit 1
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
backup_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/backups"
backup_file="$backup_directory/open-quiz-$timestamp.db"
container_backup="/data/.open-quiz-backup-$timestamp.db"

mkdir -p "$backup_directory"

cleanup() {
    docker compose exec -T open-quiz-backend /app/.venv/bin/python -c \
        "from pathlib import Path; Path('$container_backup').unlink(missing_ok=True)" \
        >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose exec -T open-quiz-backend /app/.venv/bin/python -c "
import sqlite3
source = sqlite3.connect('/data/open-quiz.db')
destination = sqlite3.connect('$container_backup')
with destination:
    source.backup(destination)
result = destination.execute('PRAGMA quick_check').fetchone()[0]
source.close()
destination.close()
if result != 'ok':
    raise RuntimeError(f'SQLite backup verification failed: {result}')
"

docker cp "$container_id:$container_backup" "$backup_file"
echo "Verified backup created at $backup_file"
