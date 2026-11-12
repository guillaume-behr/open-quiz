#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"
DATABASE_ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env.database"

backup_file=''
confirmed=false
force_key_mismatch=false

usage() {
    printf 'Usage: sh ./restore.sh [--yes] BACKUP\n\n'
    printf 'Replace the Open Quiz database with a backup made by backup.sh.\n\n'
    printf 'The current data is backed up first, then the API stops while the\n'
    printf 'backup is restored in a single transaction.\n\n'
    printf '  --yes       Do not ask for confirmation.\n'
    printf '  --force-key-mismatch\n'
    printf '              Restore although the encryption keys of\n'
    printf '              open-quiz-backend/.env differ from the backup'"'"'s.\n'
    printf '  --help, -h  Show this message.\n'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes) confirmed=true ;;
        --force-key-mismatch) force_key_mismatch=true ;;
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
acquire_lock
# Until the restore is confirmed, nothing is changed: only read and check.
[ -f "$ENV_FILE" ] || fail "missing open-quiz-backend/.env"
database_is_running || fail "the open-quiz-database container is not running"

step 'Checking the backup'
compose exec -T open-quiz-database pg_restore --list <"$backup_file" >/dev/null \
    || fail "$backup_file is not a readable pg_dump backup"

# Data encrypted with other keys would come back unreadable: two-factor
# secrets and student passwords. backup.sh records the keys' fingerprints.
if [ -f "$backup_file.meta" ]; then
    expected_keys=$(grep '_KEY_fingerprint=' "$backup_file.meta" || true)
    current_keys=$(encryption_key_fingerprints "$ENV_FILE")
    if [ "$expected_keys" != "$current_keys" ]; then
        printf '%sThe encryption keys of open-quiz-backend/.env are not the ones in use
' "$OPEN_QUIZ_BOLD"
        printf 'when this backup was taken: two-factor secrets and student passwords
'
        printf 'would not be readable. Put back the .env saved with the backup.%s
' "$OPEN_QUIZ_RESET"
        [ "$force_key_mismatch" = true ] \
            || fail "the keys do not match the backup; re-run with --force-key-mismatch to restore anyway"
    fi
else
    note "No $backup_file.meta: the encryption keys cannot be checked against the backup."
fi

if [ "$confirmed" != true ]; then
    [ -t 0 ] || fail "restoring replaces the current data; re-run with --yes to confirm"
    printf '%sThis replaces every current quiz, result and account with the backup.%s\n' \
        "$OPEN_QUIZ_BOLD" "$OPEN_QUIZ_RESET"
    printf 'Type "restore" to continue: '
    read -r answer
    [ "$answer" = restore ] || fail "restore cancelled"
fi

# Deployments from before the API had its own PostgreSQL role, as in
# update.sh: only now that the restore is confirmed.
ensure_database_environment_file "$ENV_FILE" "$DATABASE_ENV_FILE"
use_application_database_role "$ENV_FILE"

step 'Backing up the current data first'
safety_backup=$(create_backup "$SCRIPT_DIR/backups")
note "Current data saved to $safety_backup"
prune_backups "$SCRIPT_DIR/backups" "$(backup_retention)" "$safety_backup" "$backup_file"

step 'Stopping the API and the interface'
compose stop open-quiz-backend open-quiz-frontend

step 'Restoring the backup'
# The database must become the backup, not the backup laid over what is
# there: pg_restore --clean only drops what the backup contains, so a table a
# later migration created would survive next to an older alembic_version,
# and the API would refuse to start. The backup is first turned into SQL;
# then the public schema is recreated as PostgreSQL creates it and the SQL
# replayed, all in one transaction: any failure leaves the data unchanged.
if ! compose exec -T open-quiz-database sh -c '
    set -eu
    sql_file=$(mktemp)
    trap "rm -f \"$sql_file\"" EXIT
    pg_restore --no-owner --file="$sql_file"
    psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --single-transaction \
        --username=open_quiz --dbname=open_quiz \
        --command="DROP SCHEMA public CASCADE" \
        --command="CREATE SCHEMA public AUTHORIZATION pg_database_owner" \
        --command="GRANT USAGE ON SCHEMA public TO PUBLIC" \
        --command="COMMENT ON SCHEMA public IS '"'"'standard public schema'"'"'" \
        --file="$sql_file" >/dev/null
' <"$backup_file"; then
    compose up --detach --wait --wait-timeout "${OPEN_QUIZ_WAIT_TIMEOUT:-120}"
    fail "the restore failed and was rolled back; the previous data is unchanged"
fi

# pg_restore --no-owner leaves every restored object to the superuser: give
# them back to the API's role before it starts.
step "Configuring the API's PostgreSQL role"
configure_database_roles "$ENV_FILE"

step 'Starting the containers'
compose up --detach --wait --wait-timeout "${OPEN_QUIZ_WAIT_TIMEOUT:-120}"
compose ps

highlight "Restored $backup_file"
note 'Use the open-quiz-backend/.env saved with this backup, then check /api/health.'
