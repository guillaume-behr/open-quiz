#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_TEMPLATE="$SCRIPT_DIR/open-quiz-backend/.env.example"
ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

usage() {
    printf 'Usage: sh ./install-dev.sh\n'
    printf 'Create development credentials and start PostgreSQL with Docker Compose.\n'
}

case "${1:-}" in
    "") ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        usage >&2
        fail "unknown argument: $1"
        ;;
esac

for command in docker grep od sed tr mktemp; do
    command -v "$command" >/dev/null 2>&1 || fail "the '$command' command is required"
done

if docker info >/dev/null 2>&1; then
    compose() {
        docker compose "$@"
    }
elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    compose() {
        sudo docker compose "$@"
    }
else
    fail "Docker is not running or the current user cannot access it"
fi

compose version >/dev/null 2>&1 \
    || fail "Docker Compose is not available (expected: docker compose)"

validate_environment() {
    grep -q '=replace-with-' "$ENV_FILE" \
        && fail "$ENV_FILE still contains example credentials"

    for variable in DATABASE_URL POSTGRES_PASSWORD JWT_SECRET \
        TOTP_ENCRYPTION_KEY STUDENT_CREDENTIAL_ENCRYPTION_KEY \
        ADMIN_USERNAME ADMIN_PASSWORD FRONTEND_ORIGIN APP_ENV; do
        grep -Eq "^$variable=.+" "$ENV_FILE" \
            || fail "$ENV_FILE does not define $variable"
    done

    grep -q '^APP_ENV=development$' "$ENV_FILE" \
        || fail "$ENV_FILE must set APP_ENV=development"
}

random_hex() {
    byte_count=$1
    od -An -N "$byte_count" -tx1 /dev/urandom | tr -d ' \n'
}

environment_created=false

if [ -e "$ENV_FILE" ]; then
    [ -f "$ENV_FILE" ] || fail "$ENV_FILE exists but is not a regular file"
    validate_environment
    chmod 600 "$ENV_FILE"
    printf 'Keeping the existing development configuration in open-quiz-backend/.env.\n'
else
    [ -f "$ENV_TEMPLATE" ] || fail "missing development environment template: $ENV_TEMPLATE"

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
    validate_environment
    environment_created=true

    admin_username=$(sed -n 's/^ADMIN_USERNAME=//p' "$ENV_FILE")
    printf 'Development configuration created in open-quiz-backend/.env.\n'
    printf 'Administrator username: %s\n' "$admin_username"
    printf 'Administrator password: %s\n' "$admin_password"
    printf 'PostgreSQL username: open_quiz\n'
    printf 'PostgreSQL password: %s\n' "$postgres_password"
    printf 'PostgreSQL database: open_quiz\n'
    printf 'Save these development credentials; they will not be displayed again.\n'
fi

cd "$SCRIPT_DIR"
compose up --detach --wait open-quiz-database

if ! compose exec -T open-quiz-database sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql --host=127.0.0.1 --username=open_quiz --dbname=open_quiz --command="SELECT 1"' \
    >/dev/null 2>&1; then
    fail "PostgreSQL rejected the credentials from open-quiz-backend/.env; restore the configuration matching the existing volume or recreate the development database"
fi

printf '\nPostgreSQL is ready on 127.0.0.1:5432.\n'
if [ "$environment_created" = false ]; then
    printf 'Administrator credentials are stored in open-quiz-backend/.env.\n'
fi
printf 'Start the API with:\n'
printf '  cd open-quiz-backend && uv sync && uv run fastapi dev main.py\n'
printf 'Start the frontend in another terminal with:\n'
printf '  cd open-quiz-frontend && corepack enable && pnpm install --frozen-lockfile && pnpm dev\n'
