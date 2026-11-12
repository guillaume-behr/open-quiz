#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

ENV_TEMPLATE="$SCRIPT_DIR/open-quiz-backend/.env.production.example"
ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"
DATABASE_ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env.database"

usage() {
    printf 'Usage: sh ./install.sh [--domain NAME] [--help]\n\n'
    printf 'Set up a production deployment: generate every secret, write\n'
    printf 'open-quiz-backend/.env and .env.database and start the containers.\n\n'
    printf '  --domain NAME  Public domain, without https:// or a trailing slash.\n'
    printf '                 Prompted for when omitted.\n'
    printf '  --help, -h     Show this message.\n'
}

domain=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --domain)
            [ "$#" -ge 2 ] || fail '--domain requires a value'
            domain=$2
            shift
            ;;
        --domain=*) domain=${1#--domain=} ;;
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

open_quiz_banner 'First-time production setup'

require_commands git docker grep od sed tr mktemp

# Check the cheap, most common failures first: a returning user should be told
# to run update.sh rather than being sent to fix Docker.
[ -f "$ENV_TEMPLATE" ] || fail "missing production environment template: $ENV_TEMPLATE"
[ ! -e "$ENV_FILE" ] \
    || fail "$ENV_FILE already exists; keep it and run 'sh ./update.sh' instead"

if [ -z "$domain" ]; then
    printf 'Domain name for Open Quiz (for example quiz.example.com): '
    IFS= read -r domain
fi
domain=$(printf '%s' "$domain" | tr '[:upper:]' '[:lower:]')

[ -n "$domain" ] || fail 'a domain name is required'
[ "${#domain}" -le 253 ] || fail 'the domain name is too long'
printf '%s\n' "$domain" | grep -Eq '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$' \
    || fail 'enter a domain name without https://, a path, or a trailing slash'

# Confirm Docker is usable before writing any secret to disk.
setup_compose
acquire_lock

# Docker Compose's own settings, from their example: an existing file is
# kept as it is.
if [ ! -e "$SCRIPT_DIR/.env" ]; then
    compose_temporary_file=$(mktemp "$SCRIPT_DIR/.env.tmp.XXXXXX")
    (umask 077 && cp "$SCRIPT_DIR/.env.example" "$compose_temporary_file")
    chmod 600 "$compose_temporary_file"
    mv "$compose_temporary_file" "$SCRIPT_DIR/.env"
fi

step 'Generating secrets'
postgres_password=$(random_hex 32)
database_password=$(random_hex 32)
jwt_secret=$(random_hex 48)
totp_key=$(random_hex 48)
student_key=$(random_hex 48)
admin_password=$(random_hex 24)

umask 077
temporary_file=$(mktemp "$SCRIPT_DIR/open-quiz-backend/.env.tmp.XXXXXX")
trap 'rm -f "$temporary_file"; release_lock' EXIT HUP INT TERM

sed \
    -e "s|^DATABASE_PASSWORD=.*$|DATABASE_PASSWORD=$database_password|" \
    -e "s|^JWT_SECRET=.*$|JWT_SECRET=$jwt_secret|" \
    -e "s|^TOTP_ENCRYPTION_KEY=.*$|TOTP_ENCRYPTION_KEY=$totp_key|" \
    -e "s|^STUDENT_CREDENTIAL_ENCRYPTION_KEY=.*$|STUDENT_CREDENTIAL_ENCRYPTION_KEY=$student_key|" \
    -e "s|^ADMIN_PASSWORD=.*$|ADMIN_PASSWORD=$admin_password|" \
    -e "s|^FRONTEND_ORIGIN=.*$|FRONTEND_ORIGIN=https://$domain|" \
    "$ENV_TEMPLATE" > "$temporary_file"

step 'Validating the generated configuration'
validate_environment_file "$temporary_file" production

admin_username=$(sed -n 's/^ADMIN_USERNAME=//p' "$temporary_file" | head -n 1)

# The PostgreSQL superuser password goes to the database container's own
# file. A leftover one is kept: it may match an existing database volume.
if [ -f "$DATABASE_ENV_FILE" ]; then
    note "Keeping the existing $DATABASE_ENV_FILE"
else
    database_temporary_file=$(mktemp "$SCRIPT_DIR/open-quiz-backend/.env.database.tmp.XXXXXX")
    trap 'rm -f "$temporary_file" "$database_temporary_file"; release_lock' EXIT HUP INT TERM
    {
        printf '# Read by the PostgreSQL container only: the superuser password.\n'
        printf '# The API connects with its own role (DATABASE_PASSWORD in .env).\n'
        printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
    } > "$database_temporary_file"
    chmod 600 "$database_temporary_file"
    mv "$database_temporary_file" "$DATABASE_ENV_FILE"
fi

mv "$temporary_file" "$ENV_FILE"
trap release_lock EXIT
trap 'release_lock; exit 129' HUP
trap 'release_lock; exit 130' INT
trap 'release_lock; exit 143' TERM
chmod 600 "$ENV_FILE"

printf '\n'
step 'Configuration written to open-quiz-backend/.env and .env.database'
highlight "Administrator username: $admin_username"
highlight "Administrator password: $admin_password"
note 'It is stored in open-quiz-backend/.env, which keeps controlling the admin account:'
note 'protect that file and every copy of it. It will not be shown again.'
printf '\n'

# --no-pull: a fresh clone is already current, and pulling here would fail on a
# detached HEAD or move the deployment to an unexpected revision.
sh "$SCRIPT_DIR/update.sh" --no-pull

printf '\n'
highlight "Next: point your HTTPS reverse proxy at 127.0.0.1:7800 for https://$domain."
note 'Fill in the legal, privacy and accessibility values in .env, then re-run sh ./update.sh.'
note 'Deployment and backup guide: docs/deployment.md'
