#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

backup_file=''
confirmed=false

usage() {
    printf 'Usage: sh ./restore.sh [--yes] BACKUP\n\n'
    printf 'Replace the Open Quiz database with a backup made by backup.sh.\n\n'
    printf 'The current data is backed up first, then the API stops while the\n'
    printf 'backup is restored in a single transaction.\n\n'
    printf '  --yes       Do not ask for confirmation.\n'
    printf '  --help, -h  Show this message.\n'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes) confirmed=true ;;
        --help | -h)
            usage
            exit 0
            ;;
        -*)
            usage >&2
            fail "unknown argument: $1"
            ;;
        *)
            [ -z "$backup_file" ] || fail "give a single backup file"
            backup_file=$1
            ;;
    esac
    shift
done

[ -n "$backup_file" ] || {
    usage >&2
    fail "give the backup file to restore"
}
[ -f "$backup_file" ] || fail "no such backup file: $backup_file"
# Resolve the path before changing directory.
backup_file=$(CDPATH= cd -- "$(dirname -- "$backup_file")" && pwd)/$(basename -- "$backup_file")

open_quiz_banner 'Restoring your database'

cd "$SCRIPT_DIR"
require_commands docker
setup_compose
database_is_running || fail "the open-quiz-database container is not running"

step 'Checking the backup'
compose exec -T open-quiz-database pg_restore --list <"$backup_file" >/dev/null \
    || fail "$backup_file is not a readable pg_dump backup"

if [ "$confirmed" != true ]; then
    [ -t 0 ] || fail "restoring replaces the current data; re-run with --yes to confirm"
    printf '%sThis replaces every current quiz, result and account with the backup.%s\n' \
        "$OPEN_QUIZ_BOLD" "$OPEN_QUIZ_RESET"
    printf 'Type "restore" to continue: '
    read -r answer
    [ "$answer" = restore ] || fail "restore cancelled"
fi

step 'Backing up the current data first'
safety_backup=$(create_backup "$SCRIPT_DIR/backups")
note "Current data saved to $safety_backup"

step 'Stopping the API and the interface'
compose stop open-quiz-backend open-quiz-frontend

step 'Restoring the backup'
if ! compose exec -T open-quiz-database \
    pg_restore --username=open_quiz --dbname=open_quiz \
    --clean --if-exists --no-owner --single-transaction <"$backup_file"; then
    compose up --detach --wait --wait-timeout 120
    fail "the restore failed and was rolled back; the previous data is unchanged"
fi

step 'Starting the containers'
compose up --detach --wait --wait-timeout 120
compose ps

highlight "Restored $backup_file"
note 'Use the open-quiz-backend/.env saved with this backup, then check /api/health.'
