#!/usr/bin/env sh

set -eu

# shellcheck disable=SC1007 # "CDPATH= cd" empties CDPATH for this cd only.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

backup_directory="$SCRIPT_DIR/backups"
keep=''

usage() {
    printf 'Usage: sh ./backup.sh [--directory DIR] [--keep N] [--help]\n\n'
    printf 'Back up the Open Quiz database to a timestamped pg_dump file.\n\n'
    printf '  --directory DIR  Write the backup to DIR (default: backups/).\n'
    printf '  --keep N         Then delete all but the N most recent backups\n'
    printf '                   (default: OPEN_QUIZ_BACKUP_KEEP in .env, or 14).\n'
    printf '  --help, -h       Show this message.\n\n'
    printf 'A restored database also needs the encryption keys of\n'
    printf 'open-quiz-backend/.env. Keep a copy of that file, but not next to the\n'
    printf 'backups: together they give away what the keys protect.\n'
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
# A backup taken during an update or a restore could catch the database
# half-way: fail instead, so that a scheduled run reports it.
acquire_lock
database_is_running || fail "the open-quiz-database container is not running"

step 'Dumping PostgreSQL'
backup_file=$(create_backup "$backup_directory")
highlight "Backup written to $backup_file"

keep=${keep:-$(backup_retention)}
step "Keeping the $keep most recent backups"
prune_backups "$backup_directory" "$keep" "$backup_file"

note 'Copy it to separate protected storage. Keep open-quiz-backend/.env and'
note '.env.database too, but apart from the backups: they hold the keys.'
