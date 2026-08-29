#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

ENV_TEMPLATE="$SCRIPT_DIR/open-quiz-backend/.env.example"
ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"
COMPOSE_BASE="$SCRIPT_DIR/docker-compose.yml"
COMPOSE_DEV="$SCRIPT_DIR/docker-compose.dev.yml"

# The development override publishes PostgreSQL on 127.0.0.1:5432 so that the
# API can run on the host. Without it the container is reachable only from the
# internal Docker network and the API fails with "connection refused".
dev_compose() {
    compose -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" "$@"
}

usage() {
    printf 'Usage: sh ./install-dev.sh [--help]\n\n'
    printf 'Create development credentials and start PostgreSQL with Docker Compose.\n\n'
    printf '  --help, -h  Show this message.\n'
}

case "${1:-}" in
    "") ;;
    --help | -h)
        usage
        exit 0
        ;;
    *)
        usage >&2
        fail "unknown argument: $1"
        ;;
esac

open_quiz_banner 'Local development setup'

require_commands docker grep od sed tr mktemp
[ -f "$COMPOSE_BASE" ] || fail "missing Docker Compose file: $COMPOSE_BASE"
[ -f "$COMPOSE_DEV" ] || fail "missing development override: $COMPOSE_DEV"
setup_compose

environment_created=false

if [ -e "$ENV_FILE" ]; then
    [ -f "$ENV_FILE" ] || fail "$ENV_FILE exists but is not a regular file"
    validate_environment_file "$ENV_FILE" development
    chmod 600 "$ENV_FILE"
    step 'Keeping the existing development configuration in open-quiz-backend/.env'
else
    [ -f "$ENV_TEMPLATE" ] || fail "missing development environment template: $ENV_TEMPLATE"

    step 'Generating development credentials'
    postgres_password=$(random_hex 32)
    jwt_secret=$(random_hex 48)
    totp_key=$(random_hex 48)
    student_key=$(random_hex 48)
    admin_password=$(random_hex 24)

    umask 077
    temporary_file=$(mktemp "$SCRIPT_DIR/open-quiz-backend/.env.tmp.XXXXXX")
    trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

    sed \
        -e "s|^POSTGRES_PASSWORD=.*$|POSTGRES_PASSWORD=$postgres_password|" \
        -e "s|^JWT_SECRET=.*$|JWT_SECRET=$jwt_secret|" \
        -e "s|^TOTP_ENCRYPTION_KEY=.*$|TOTP_ENCRYPTION_KEY=$totp_key|" \
        -e "s|^STUDENT_CREDENTIAL_ENCRYPTION_KEY=.*$|STUDENT_CREDENTIAL_ENCRYPTION_KEY=$student_key|" \
        -e "s|^ADMIN_PASSWORD=.*$|ADMIN_PASSWORD=$admin_password|" \
        "$ENV_TEMPLATE" > "$temporary_file"

    mv "$temporary_file" "$ENV_FILE"
    trap - EXIT HUP INT TERM
    chmod 600 "$ENV_FILE"
    validate_environment_file "$ENV_FILE" development
    environment_created=true

    admin_username=$(sed -n 's/^ADMIN_USERNAME=//p' "$ENV_FILE" | head -n 1)
    step 'Development configuration created in open-quiz-backend/.env'
    highlight "Administrator username: $admin_username"
    highlight "Administrator password: $admin_password"
    highlight "PostgreSQL open_quiz / $postgres_password (database: open_quiz)"
    note 'Save these development credentials; they will not be displayed again.'
fi

cd "$SCRIPT_DIR"
step 'Starting PostgreSQL'
dev_compose up --detach --wait open-quiz-database

if ! dev_compose exec -T open-quiz-database sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql --host=127.0.0.1 --username=open_quiz --dbname=open_quiz --command="SELECT 1"' \
    >/dev/null 2>&1; then
    fail "PostgreSQL rejected the credentials from open-quiz-backend/.env; restore the configuration matching the existing volume or recreate the development database"
fi

printf '\n'
highlight 'PostgreSQL is ready on 127.0.0.1:5432.'
if [ "$environment_created" = false ]; then
    note 'Administrator credentials are stored in open-quiz-backend/.env.'
fi
printf '\n'
step 'Start the API'
note 'cd open-quiz-backend && uv sync && uv run fastapi dev main.py'
step 'Start the interface, in another terminal'
note 'cd open-quiz-frontend && corepack enable && pnpm install --frozen-lockfile && pnpm dev'
