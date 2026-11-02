# Shared helpers for the Open Quiz shell scripts.
# This file is sourced, never executed directly.

# Brand purple is rgb(138, 79, 255), the --primary token of the interface.
# Fall back to the closest 256-colour purple, and to no colour at all when the
# output is redirected, NO_COLOR is set, or the terminal is not capable.
OPEN_QUIZ_PURPLE=''
OPEN_QUIZ_BOLD=''
OPEN_QUIZ_DIM=''
OPEN_QUIZ_RED=''
OPEN_QUIZ_RESET=''

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
    case "${COLORTERM:-}" in
        truecolor | 24bit)
            OPEN_QUIZ_PURPLE=$(printf '\033[38;2;138;79;255m')
            ;;
        *)
            OPEN_QUIZ_PURPLE=$(printf '\033[38;5;141m')
            ;;
    esac
    OPEN_QUIZ_BOLD=$(printf '\033[1m')
    OPEN_QUIZ_DIM=$(printf '\033[2m')
    OPEN_QUIZ_RED=$(printf '\033[31m')
    OPEN_QUIZ_RESET=$(printf '\033[0m')
fi

open_quiz_banner() {
    subtitle=${1:-}
    printf '%s\n' "$OPEN_QUIZ_PURPLE"
    cat <<'LOGO'
 ██████  ██████  ███████ ███    ██    ██████  ██    ██ ██ ███████
██    ██ ██   ██ ██      ████   ██   ██    ██ ██    ██ ██    ███
██    ██ ██████  █████   ██ ██  ██   ██    ██ ██    ██ ██   ███
██    ██ ██      ██      ██  ██ ██   ██ ▄▄ ██ ██    ██ ██  ███
 ██████  ██      ███████ ██   ████    ██████   ██████  ██ ███████
                                         ▀▀
LOGO
    printf '%s' "$OPEN_QUIZ_RESET"
    if [ -n "$subtitle" ]; then
        printf '%s%s%s\n' "$OPEN_QUIZ_DIM" "$subtitle" "$OPEN_QUIZ_RESET"
    fi
    printf '\n'
}

fail() {
    printf '%sError:%s %s\n' "$OPEN_QUIZ_RED" "$OPEN_QUIZ_RESET" "$1" >&2
    exit 1
}

step() {
    printf '%s==>%s %s\n' "$OPEN_QUIZ_PURPLE" "$OPEN_QUIZ_RESET" "$1"
}

note() {
    printf '%s    %s%s\n' "$OPEN_QUIZ_DIM" "$1" "$OPEN_QUIZ_RESET"
}

highlight() {
    printf '%s%s%s\n' "$OPEN_QUIZ_BOLD" "$1" "$OPEN_QUIZ_RESET"
}

require_commands() {
    for required_command in "$@"; do
        command -v "$required_command" >/dev/null 2>&1 \
            || fail "the '$required_command' command is required"
    done
}

# Define compose() against a reachable Docker daemon, retrying through sudo so
# that a user outside the docker group still gets a working deployment.
setup_compose() {
    if docker info >/dev/null 2>&1; then
        compose() {
            docker compose "$@"
        }
    elif ! command -v sudo >/dev/null 2>&1; then
        fail "Docker is not running, or this user cannot reach it. Start Docker, or add your user to the 'docker' group and open a new session."
    elif sudo -n docker info >/dev/null 2>&1; then
        # Cached or passwordless sudo: no prompt needed.
        compose() {
            sudo docker compose "$@"
        }
    elif [ -t 0 ]; then
        # Only ever prompt for a password when someone is there to type it;
        # a piped or scheduled run must fail instead of hanging forever.
        step 'Docker needs administrator rights for this user'
        note "Add your user to the 'docker' group to avoid this prompt."
        sudo docker info >/dev/null 2>&1 \
            || fail "Docker is not running, or this user cannot reach it even with sudo."
        compose() {
            sudo docker compose "$@"
        }
    else
        fail "Docker is unreachable for this user and no terminal is available to confirm sudo. Add your user to the 'docker' group, or re-run from an interactive shell."
    fi

    compose version >/dev/null 2>&1 \
        || fail "Docker Compose is not available (expected: docker compose)"
}

# Generate a hexadecimal secret of the requested byte length.
random_hex() {
    od -An -N "$1" -tx1 /dev/urandom | tr -d ' \n'
}

# Reject an environment file that still carries template values or is missing a
# required variable, so a broken deployment fails here instead of at runtime.
validate_environment_file() {
    environment_file=$1
    expected_app_env=$2

    ! grep -q '=replace-with-' "$environment_file" \
        || fail "$environment_file still contains example credentials"

    # Production connects as the API's own role (DATABASE_PASSWORD); the
    # development database is reached as the PostgreSQL superuser.
    case "$expected_app_env" in
        production) database_password_variable=DATABASE_PASSWORD ;;
        *) database_password_variable=POSTGRES_PASSWORD ;;
    esac
    for variable in DATABASE_URL "$database_password_variable" JWT_SECRET \
        TOTP_ENCRYPTION_KEY STUDENT_CREDENTIAL_ENCRYPTION_KEY \
        ADMIN_USERNAME ADMIN_PASSWORD FRONTEND_ORIGIN APP_ENV; do
        grep -Eq "^$variable=.+" "$environment_file" \
            || fail "$environment_file does not define $variable"
    done

    grep -q "^APP_ENV=$expected_app_env\$" "$environment_file" \
        || fail "$environment_file must set APP_ENV=$expected_app_env"
}

# Dump the running database to a new file in $1, readable by its owner only,
# and print the file's path. The dump holds students' personal data.
create_backup() {
    backup_directory=$1
    (umask 077 && mkdir -p "$backup_directory")
    chmod 700 "$backup_directory"
    backup_stem="$backup_directory/open-quiz-$(date -u +%Y-%m-%dT%H%M%SZ)"
    backup_file="$backup_stem.dump"
    # Two backups within one second (a restore's safety copy, say) must not
    # overwrite each other.
    suffix=1
    while [ -e "$backup_file" ]; do
        suffix=$((suffix + 1))
        backup_file="$backup_stem-$suffix.dump"
    done
    partial_file="$backup_file.partial"
    if ! (umask 077 && compose exec -T open-quiz-database \
        pg_dump --username=open_quiz --dbname=open_quiz --format=custom \
        >"$partial_file"); then
        rm -f "$partial_file"
        fail "pg_dump failed; no backup was written"
    fi
    if ! compose exec -T open-quiz-database pg_restore --list \
        <"$partial_file" >/dev/null; then
        rm -f "$partial_file"
        fail "the new backup cannot be read back; it was discarded"
    fi
    mv "$partial_file" "$backup_file"
    printf '%s\n' "$backup_file"
}

database_is_running() {
    compose ps --status running --services 2>/dev/null \
        | grep -qx open-quiz-database
}

# The role the API connects as. scripts/database-roles.sql creates it.
DATABASE_APP_ROLE=open_quiz_app

# Print the value an environment file gives to a variable (empty when unset).
environment_value() {
    sed -n "s/^$2=//p" "$1" | tail -n 1
}

# The database container reads its superuser password from its own file, so
# that it never receives the application's secrets. Create that file from
# open-quiz-backend/.env on deployments that predate it.
ensure_database_environment_file() {
    environment_file=$1
    database_environment_file=$2
    if [ -f "$database_environment_file" ]; then
        chmod 600 "$database_environment_file"
        return 0
    fi
    superuser_password=$(environment_value "$environment_file" POSTGRES_PASSWORD)
    [ -n "$superuser_password" ] \
        || fail "$database_environment_file is missing, and $environment_file has no POSTGRES_PASSWORD to create it from"
    database_temporary_file=$(umask 077 && mktemp "$database_environment_file.tmp.XXXXXX")
    {
        printf '# Read by the PostgreSQL container only: the superuser password.\n'
        printf '# The API connects with its own role (DATABASE_PASSWORD in .env).\n'
        printf 'POSTGRES_PASSWORD=%s\n' "$superuser_password"
    } >"$database_temporary_file"
    chmod 600 "$database_temporary_file"
    mv "$database_temporary_file" "$database_environment_file"
    note "Created $database_environment_file with the PostgreSQL superuser password."
}

# Move a production .env from the superuser to the API's own role: give it a
# DATABASE_PASSWORD, point DATABASE_URL at the role and drop the superuser
# password, which now lives in the database container's file only. Run
# ensure_database_environment_file first, which copies that password over.
use_application_database_role() {
    environment_file=$1
    grep -Eq '^DATABASE_PASSWORD=.+' "$environment_file" && return 0
    step "Moving the API to its own PostgreSQL role ($DATABASE_APP_ROLE)"
    application_temporary_file=$(umask 077 && mktemp "$environment_file.tmp.XXXXXX")
    sed \
        -e '/^POSTGRES_PASSWORD=/d' \
        -e "s|^DATABASE_URL=\\(postgresql[^:]*://\\)open_quiz@|DATABASE_URL=\\1$DATABASE_APP_ROLE@|" \
        "$environment_file" >"$application_temporary_file"
    if [ -n "$(tail -c 1 "$application_temporary_file")" ]; then
        printf '\n' >>"$application_temporary_file"
    fi
    printf 'DATABASE_PASSWORD=%s\n' "$(random_hex 32)" >>"$application_temporary_file"
    chmod 600 "$application_temporary_file"
    mv "$application_temporary_file" "$environment_file"
    grep -Eq "^DATABASE_URL=postgresql[^:]*://$DATABASE_APP_ROLE@" "$environment_file" \
        || note "DATABASE_URL in $environment_file does not name the $DATABASE_APP_ROLE role; update it by hand."
}

# Create or update the API's role and give it the database and its objects,
# as the superuser over the container's local socket. Needs the database
# container running and $SCRIPT_DIR set to the repository root.
configure_database_roles() {
    environment_file=$1
    application_password=$(environment_value "$environment_file" DATABASE_PASSWORD)
    [ -n "$application_password" ] \
        || fail "$environment_file does not define DATABASE_PASSWORD"
    # The password is spliced into a psql command: keep it to safe characters.
    printf '%s\n' "$application_password" | grep -Eq '^[A-Za-z0-9._~-]{16,}$' \
        || fail "DATABASE_PASSWORD must be at least 16 letters, digits or . _ ~ - characters"
    {
        printf '%s\n' "\\set app_password '$application_password'"
        cat "$SCRIPT_DIR/scripts/database-roles.sql"
    } | compose exec -T open-quiz-database psql --quiet --no-psqlrc \
        --set=ON_ERROR_STOP=1 --username=open_quiz --dbname=open_quiz >/dev/null \
        || fail "could not configure the $DATABASE_APP_ROLE PostgreSQL role"
}
