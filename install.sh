#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_TEMPLATE="$SCRIPT_DIR/open-quiz-backend/.env.production.example"
ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

for command in git docker grep od sed tr mktemp; do
    command -v "$command" >/dev/null 2>&1 || fail "the '$command' command is required"
done

docker compose version >/dev/null 2>&1 || fail "Docker Compose is not available (expected: docker compose)"
[ -f "$ENV_TEMPLATE" ] || fail "missing production environment template: $ENV_TEMPLATE"
[ ! -e "$ENV_FILE" ] || fail "$ENV_FILE already exists; keep it and run sh ./update.sh instead"

printf 'Domain name for Open Quiz (for example quiz.example.com): '
IFS= read -r domain
domain=$(printf '%s' "$domain" | tr '[:upper:]' '[:lower:]')

[ "${#domain}" -le 253 ] || fail "the domain name is too long"
printf '%s\n' "$domain" | grep -Eq '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$' \
    || fail "enter a domain name without https://, a path, or a trailing slash"

random_hex() {
    byte_count=$1
    od -An -N "$byte_count" -tx1 /dev/urandom | tr -d ' \n'
}

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
    -e "s|^FRONTEND_ORIGIN=.*$|FRONTEND_ORIGIN=https://$domain|" \
    "$ENV_TEMPLATE" > "$temporary_file"

if grep -q '=replace-with-' "$temporary_file"; then
    fail "the generated configuration still contains an example value"
fi

for variable in DATABASE_URL POSTGRES_PASSWORD JWT_SECRET TOTP_ENCRYPTION_KEY \
    STUDENT_CREDENTIAL_ENCRYPTION_KEY ADMIN_USERNAME ADMIN_PASSWORD \
    FRONTEND_ORIGIN APP_ENV; do
    grep -Eq "^$variable=.+" "$temporary_file" \
        || fail "the production template does not define $variable"
done

grep -q '^APP_ENV=production$' "$temporary_file" \
    || fail "the production template must set APP_ENV=production"

admin_username=$(sed -n 's/^ADMIN_USERNAME=//p' "$temporary_file")

mv "$temporary_file" "$ENV_FILE"
trap - EXIT HUP INT TERM
chmod 600 "$ENV_FILE"

printf '\nConfiguration created in open-quiz-backend/.env.\n'
printf 'Administrator username: %s\n' "$admin_username"
printf 'Administrator password: %s\n' "$admin_password"
printf 'Save this password now. It will not be displayed again.\n\n'
printf 'Launching the update and deployment script...\n'

cd "$SCRIPT_DIR"
sh ./update.sh

printf '\nOpen Quiz is running locally on http://127.0.0.1:7800.\n'
printf 'Configure your HTTPS reverse proxy for https://%s.\n' "$domain"
