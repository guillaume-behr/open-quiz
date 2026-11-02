#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

backup_directory="$SCRIPT_DIR/backups"
keep=''

usage() {
    printf 'Usage: sh ./backup.sh [--directory DIR] [--keep N] [--help]\n\n'
    printf 'Back up the Open Quiz database to a timestamped pg_dump file.\n\n'
    printf '  --directory DIR  Write the backup to DIR (default: backups/).\n'
    printf '  --keep N         Then delete all but the N most recent backups.\n'
    printf '  --help, -h       Show this message.\n\n'
    printf 'Keep a copy of open-quiz-backend/.env with the backups: without its\n'
    printf 'encryption keys, a restored database cannot be fully used.\n'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --directory)
            [ "$#" -ge 2 ] || fail "--directory needs a value"
            backup_directory=$2
            shift
            ;;
        --keep)
            [ "$#" -ge 2 ] || fail "--keep needs a value"
            case "$2" in
                '' | *[!0-9]* | 0) fail "--keep needs a positive whole number" ;;
            esac
            keep=$2
            shift
            ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            usage >&2
            fail "unknown argument: $1"
            ;;
    esac
    shift
done

open_quiz_banner 'Backing up your database'

cd "$SCRIPT_DIR"
require_commands docker
setup_compose
database_is_running || fail "the open-quiz-database container is not running"

step 'Dumping PostgreSQL'
backup_file=$(create_backup "$backup_directory")
highlight "Backup written to $backup_file"

if [ -n "$keep" ]; then
    step "Keeping the $keep most recent backups"
    # Newest first, by modification time: two backups of the same second
    # differ only by a suffix, which does not sort chronologically.
    ls -1t "$backup_directory"/open-quiz-*.dump | tail -n "+$((keep + 1))" \
        | while IFS= read -r old_backup; do
            rm -f "$old_backup"
            note "Removed $old_backup"
        done
fi

note 'Copy it, with open-quiz-backend/.env, to separate protected storage.'
