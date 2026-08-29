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

    for variable in DATABASE_URL POSTGRES_PASSWORD JWT_SECRET \
        TOTP_ENCRYPTION_KEY STUDENT_CREDENTIAL_ENCRYPTION_KEY \
        ADMIN_USERNAME ADMIN_PASSWORD FRONTEND_ORIGIN APP_ENV; do
        grep -Eq "^$variable=.+" "$environment_file" \
            || fail "$environment_file does not define $variable"
    done

    grep -q "^APP_ENV=$expected_app_env\$" "$environment_file" \
        || fail "$environment_file must set APP_ENV=$expected_app_env"
}
