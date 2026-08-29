#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"
pull=true

usage() {
    printf 'Usage: sh ./update.sh [--no-pull] [--help]\n\n'
    printf 'Update an Open Quiz deployment: fetch the latest revision, rebuild\n'
    printf 'the containers and wait until they report healthy.\n\n'
    printf '  --no-pull   Rebuild and restart without fetching a new revision.\n'
    printf '  --help, -h  Show this message.\n'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-pull) pull=false ;;
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

open_quiz_banner 'Updating your deployment'

cd "$SCRIPT_DIR"
require_commands docker
setup_compose

[ -f "$ENV_FILE" ] \
    || fail "missing open-quiz-backend/.env; run 'sh ./install.sh' to create it"

if [ "$pull" = true ]; then
    require_commands git
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        || fail "this directory is not a Git clone; re-run with --no-pull, or clone the repository"

    # A dirty tree makes --ff-only fail with a confusing message, so say what
    # is actually wrong and leave the deployment untouched.
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        fail "the working tree has local changes; commit, stash or discard them, or re-run with --no-pull"
    fi

    previous_version=$(git describe --tags --always 2>/dev/null || echo 'unknown')
    step 'Fetching the latest revision'
    git pull --ff-only
    current_version=$(git describe --tags --always 2>/dev/null || echo 'unknown')

    if [ "$previous_version" = "$current_version" ]; then
        note "Already up to date ($current_version)."
    else
        note "$previous_version -> $current_version"
        printf '%sBack up PostgreSQL before applying a version change.%s\n' \
            "$OPEN_QUIZ_BOLD" "$OPEN_QUIZ_RESET"
        note 'See docs/deployment.md for the pg_dump procedure.'
    fi
else
    step 'Skipping the revision fetch (--no-pull)'
fi

step 'Validating the Compose configuration'
compose config --quiet

step 'Building and starting the containers'
compose up --detach --build --remove-orphans --wait --wait-timeout 120

step 'Deployment status'
compose ps

frontend_origin=$(sed -n 's/^FRONTEND_ORIGIN=//p' "$ENV_FILE" | head -n 1)
printf '\n'
highlight 'Open Quiz is running on http://127.0.0.1:7800.'
if [ -n "$frontend_origin" ]; then
    note "Publish it behind your HTTPS reverse proxy for $frontend_origin."
    note "Check the instance with: curl --fail $frontend_origin/api/health"
fi
