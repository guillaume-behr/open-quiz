#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/scripts/common.sh"

ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env"
DATABASE_ENV_FILE="$SCRIPT_DIR/open-quiz-backend/.env.database"
BACKUP_DIRECTORY="$SCRIPT_DIR/backups"
# The commit of the last deployment that came up healthy.
DEPLOYED_REVISION_FILE="$BACKUP_DIRECTORY/deployed-revision"
# Images of earlier deployments, kept so that a rollback needs no rebuild.
ROLLBACK_IMAGE_REPOSITORY=open-quiz-rollback
ROLLBACK_IMAGES_KEPT=3
pull=true
backup=true
version=''
rollback=false
confirmed=false
wait_timeout=${OPEN_QUIZ_WAIT_TIMEOUT:-120}

usage() {
    printf 'Usage: sh ./update.sh [--version TAG] [--no-pull] [--no-backup]\n'
    printf '                      [--wait-timeout SECONDS]\n'
    printf '       sh ./update.sh --rollback [--yes] [--wait-timeout SECONDS]\n\n'
    printf 'Update an Open Quiz deployment: fetch a new revision, rebuild the\n'
    printf 'containers and wait until they report healthy. The database is\n'
    printf 'backed up to backups/ first, with what a rollback needs.\n\n'
    printf '  --version TAG          Install this release (e.g. v1.0.0) instead of\n'
    printf '                         the tip of the branch, which holds unreleased\n'
    printf '                         changes.\n'
    printf '  --no-pull              Rebuild and restart without fetching a new\n'
    printf '                         revision.\n'
    printf '  --no-backup            Skip the database backup (a rollback then\n'
    printf '                         cannot restore the data).\n'
    printf '  --rollback             Return to the code, images and data of the\n'
    printf '                         deployment before the last update.\n'
    printf '  --yes                  With --rollback: do not ask for confirmation.\n'
    printf '  --wait-timeout SECONDS How long to wait for healthy containers\n'
    printf '                         (default 120, or OPEN_QUIZ_WAIT_TIMEOUT).\n'
    printf '  --help, -h             Show this message.\n'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-pull) pull=false ;;
        --no-backup) backup=false ;;
        --rollback) rollback=true ;;
        --yes) confirmed=true ;;
        --version)
            [ "$#" -ge 2 ] || fail "--version needs a tag, such as v1.0.0"
            version=$2
            shift
            ;;
        --wait-timeout)
            [ "$#" -ge 2 ] || fail "--wait-timeout needs a number of seconds"
            wait_timeout=$2
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

case "$wait_timeout" in
    '' | *[!0-9]*) fail "--wait-timeout must be a whole number of seconds" ;;
esac
[ "$rollback" = false ] || [ -z "$version" ] \
    || fail "--rollback returns to the previous deployment; it takes no --version"
[ "$rollback" = true ] || [ "$confirmed" = false ] \
    || fail "--yes only applies to --rollback"
[ -z "$version" ] || [ "$pull" = true ] \
    || fail "--version fetches a release; it cannot be combined with --no-pull"

cd "$SCRIPT_DIR"

# Print the value of KEY in a KEY=value state file.
state_value() {
    sed -n "s/^$2=//p" "$1" | tail -n 1
}

# The image a service's container runs, as "reference id", or nothing when
# the service has no container.
service_image() {
    container=$(compose ps --all --quiet "$1" 2>/dev/null | head -n 1)
    [ -n "$container" ] || return 0
    docker_cli inspect --format '{{.Config.Image}} {{.Image}}' "$container"
}

# Keep the newest rollback images of a service, drop older ones.
prune_rollback_images() {
    docker_cli image ls "$ROLLBACK_IMAGE_REPOSITORY" --format '{{.Tag}}' \
        | grep "^$1-" | sort -r | tail -n "+$((ROLLBACK_IMAGES_KEPT + 1))" \
        | while read -r old_tag; do
            docker_cli image rm "$ROLLBACK_IMAGE_REPOSITORY:$old_tag" >/dev/null
        done
}

# Print the newest rollback record, if any.
latest_rollback_state() {
    find "$BACKUP_DIRECTORY" -maxdepth 1 -name '*.rollback' 2>/dev/null \
        | sort | tail -n 1
}

roll_back() {
    open_quiz_banner 'Rolling back the last update'
    require_commands docker
    setup_compose
    acquire_lock
    [ -f "$ENV_FILE" ] || fail "missing open-quiz-backend/.env"

    state_file=$(latest_rollback_state)
    [ -n "$state_file" ] \
        || fail "no update to roll back: update.sh records one before each update"
    commit=$(state_value "$state_file" commit)
    backup_file=$(state_value "$state_file" backup)

    printf 'Previous deployment: %s\n' "$(state_value "$state_file" version)"
    if [ -n "$backup_file" ]; then
        printf 'Data: the backup made before the update, %s\n' "$backup_file"
        [ -f "$backup_file" ] || fail "the backup $backup_file no longer exists"
    else
        printf '%sNo backup was made before the update: the code and images go\n' \
            "$OPEN_QUIZ_BOLD"
        printf 'back, the data stays as it is now.%s\n' "$OPEN_QUIZ_RESET"
    fi
    if [ "$confirmed" != true ]; then
        [ -t 0 ] || fail "rolling back replaces the current data; re-run with --yes to confirm"
        printf '%sEverything written since the update is lost.%s\n' \
            "$OPEN_QUIZ_BOLD" "$OPEN_QUIZ_RESET"
        printf 'Type "rollback" to continue: '
        read -r answer
        [ "$answer" = rollback ] || fail "rollback cancelled"
    fi

    # The old code first, so that the old images run with the old Compose
    # file and scripts.
    if [ -n "$commit" ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if [ "$(git rev-parse HEAD)" != "$commit" ]; then
            [ -z "$(git status --porcelain 2>/dev/null)" ] \
                || fail "the working tree has local changes; commit, stash or discard them first"
            step "Checking out the previous revision ($commit)"
            git checkout --quiet --detach "$commit"
        fi
    fi

    step 'Putting back the previous images'
    for service in backend frontend; do
        rollback_image=$(state_value "$state_file" "${service}_rollback_image")
        image_name=$(state_value "$state_file" "${service}_image_name")
        [ -n "$rollback_image" ] && [ -n "$image_name" ] \
            || fail "the rollback record $state_file names no $service image"
        docker_cli image inspect "$rollback_image" >/dev/null 2>&1 \
            || fail "the image $rollback_image is gone; rebuild instead with: sh ./update.sh --no-pull"
        docker_cli image tag "$rollback_image" "$image_name"
    done

    # Then the data, which restore.sh brings back while the API is stopped,
    # before it starts the containers again on the old images.
    if [ -n "$backup_file" ]; then
        OPEN_QUIZ_WAIT_TIMEOUT=$wait_timeout \
            sh "$SCRIPT_DIR/restore.sh" --yes "$backup_file"
    else
        step 'Starting the containers'
        compose up --detach --remove-orphans --wait --wait-timeout "$wait_timeout"
    fi

    [ -z "$commit" ] || printf '%s\n' "$commit" >"$DEPLOYED_REVISION_FILE"
    # Done: a second --rollback must not go back to the same record.
    mv "$state_file" "$state_file.done"

    compose ps
    highlight 'Rolled back to the deployment before the last update.'
    if [ -n "$commit" ]; then
        note 'This checkout is now detached at the previous revision. To update again:'
        note '  sh ./update.sh --version <tag>, or return to the branch with'
        note '  git checkout <branch> and then sh ./update.sh'
    fi
}

# roll_back checks out an older copy of this script while it runs. The shell
# parsed this whole block, exit included, before running it: nothing more is
# read from the file once the rollback starts.
if [ "$rollback" = true ]; then
    roll_back
    exit 0
fi

open_quiz_banner 'Updating your deployment'

require_commands docker
setup_compose
acquire_lock

[ -f "$ENV_FILE" ] \
    || fail "missing open-quiz-backend/.env; run 'sh ./install.sh' to create it"

# The revision now running: the last healthy deployment, or what is checked
# out when none was recorded (deployments from before the record existed).
previous_commit=''
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    previous_commit=$(cat "$DEPLOYED_REVISION_FILE" 2>/dev/null || git rev-parse HEAD)
fi
previous_version=$(git describe --tags --always "${previous_commit:-HEAD}" 2>/dev/null || echo 'unknown')

if [ "$pull" = true ]; then
    require_commands git
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        || fail "this directory is not a Git clone; re-run with --no-pull, or clone the repository"

    # A dirty tree makes --ff-only fail with a confusing message, so say what
    # is actually wrong and leave the deployment untouched.
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        fail "the working tree has local changes; commit, stash or discard them, or re-run with --no-pull"
    fi

    if [ -n "$version" ]; then
        step "Fetching release $version"
        git fetch --quiet --tags origin
        git rev-parse --quiet --verify "refs/tags/$version^{commit}" >/dev/null \
            || fail "no release tagged $version; see CHANGELOG.md for the versions"
        git checkout --quiet --detach "$version"
    elif ! branch=$(git symbolic-ref --quiet --short HEAD); then
        # A release (--version) or a rollback left the checkout detached,
        # where a pull has no branch to follow.
        fail "this deployment runs a release, not a branch ($previous_version); update with --version <tag>, or follow the branch again with: git checkout <branch>, then sh ./update.sh"
    else
        step "Fetching the latest revision of $branch"
        git pull --ff-only
        note "This deploys the tip of $branch, unreleased changes included: read the"
        note '[Unreleased] section of CHANGELOG.md, or install a release with --version.'
    fi
    current_version=$(git describe --tags --always 2>/dev/null || echo 'unknown')

    if [ "$previous_version" = "$current_version" ]; then
        note "Already up to date ($current_version)."
    else
        note "$previous_version -> $current_version"
    fi
else
    step 'Skipping the revision fetch (--no-pull)'
fi

step 'Validating the Compose configuration'
compose config --quiet

# A Compose setting given only in the shell holds for this run, and is lost
# on the next one started without it: it belongs in the root .env.
for variable in OPEN_QUIZ_SUBNET_PREFIX OPEN_QUIZ_API_WORKERS \
    OPEN_QUIZ_API_PIDS OPEN_QUIZ_API_MEMORY OPEN_QUIZ_PROXY_MEMORY; do
    if eval "[ -n \"\${$variable+set}\" ]" \
        && ! grep -q "^$variable=" "$SCRIPT_DIR/.env" 2>/dev/null; then
        note "Warning: $variable is set in the shell but not in .env; the next update will not see it."
    fi
done
if [ -n "${VITE_API_URL:-}" ]; then
    note 'Warning: VITE_API_URL is ignored: the deployment serves the API under the interface origin.'
fi

backup_file=''
if [ "$backup" = false ]; then
    step 'Skipping the database backup (--no-backup)'
elif database_is_running; then
    step 'Backing up the database'
    backup_file=$(create_backup "$BACKUP_DIRECTORY")
    note "Saved to $backup_file; restore it with: sh ./restore.sh $backup_file"
    prune_backups "$BACKUP_DIRECTORY" "$(backup_retention)" "$backup_file"
else
    step 'Skipping the database backup: the database is not running yet'
fi

# What a rollback needs, recorded before anything is rebuilt: the running
# revision, the backup above and the running images, tagged so that the
# build below does not leave them unnamed.
backend_image=$(service_image open-quiz-backend)
frontend_image=$(service_image open-quiz-frontend)
state_file=$(latest_rollback_state)
if [ -n "$state_file" ] && ! grep -qx 'completed=yes' "$state_file"; then
    # The last update never came up healthy, and what runs now is its
    # failed attempt: a retry keeps the record of the deployment before it.
    step 'Keeping the rollback record of the unfinished update'
    note "$state_file"
elif [ -n "$backend_image" ] && [ -n "$frontend_image" ]; then
    step 'Recording what a rollback needs'
    (umask 077 && mkdir -p "$BACKUP_DIRECTORY")
    stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
    state_file="$BACKUP_DIRECTORY/open-quiz-$stamp.rollback"
    {
        printf 'commit=%s\n' "$previous_commit"
        printf 'version=%s\n' "$previous_version"
        printf 'backup=%s\n' "$backup_file"
    } >"$state_file"
    for service in backend frontend; do
        if [ "$service" = backend ]; then
            image=$backend_image
        else
            image=$frontend_image
        fi
        rollback_image="$ROLLBACK_IMAGE_REPOSITORY:$service-$stamp"
        docker_cli image tag "${image#* }" "$rollback_image"
        printf '%s_image_name=%s\n%s_rollback_image=%s\n' \
            "$service" "${image%% *}" "$service" "$rollback_image" >>"$state_file"
        prune_rollback_images "$service"
    done
    note "Saved to $state_file"
else
    state_file=''
    step 'Nothing to roll back to yet: no containers are running'
fi

# Deployments from before the API had its own PostgreSQL role: split the
# superuser password into the database's file, then switch the API's role.
# Only now, once the revision is fetched and the data backed up: a check that
# fails above leaves both files as they were, and the role is created right
# below. The running containers keep their settings until they are recreated.
ensure_database_environment_file "$ENV_FILE" "$DATABASE_ENV_FILE"
use_application_database_role "$ENV_FILE"

step 'Starting the database'
compose up --detach --wait --wait-timeout "$wait_timeout" open-quiz-database

step "Configuring the API's PostgreSQL role"
configure_database_roles "$ENV_FILE"

step 'Building and starting the containers'
if ! compose up --detach --build --remove-orphans --wait \
    --wait-timeout "$wait_timeout"; then
    compose ps
    printf '\n'
    highlight 'The update did not come up healthy.'
    note 'Logs: docker compose logs open-quiz-backend'
    note "A slow migration may need more time: sh ./update.sh --no-pull --wait-timeout $((wait_timeout * 5))"
    if [ -n "$backend_image" ]; then
        note 'Return to the previous code, images and data with:'
        note '  sh ./update.sh --rollback'
    fi
    exit 1
fi

# A healthy deployment is what the next update can return to; its own
# record stays, for a rollback should it misbehave later.
[ -z "$state_file" ] || printf 'completed=yes\n' >>"$state_file"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    (umask 077 && mkdir -p "$BACKUP_DIRECTORY")
    git rev-parse HEAD >"$DEPLOYED_REVISION_FILE"
fi

step 'Deployment status'
compose ps

frontend_origin=$(sed -n 's/^FRONTEND_ORIGIN=//p' "$ENV_FILE" | head -n 1)
printf '\n'
highlight 'Open Quiz is running on http://127.0.0.1:7800.'
if [ -n "$frontend_origin" ]; then
    note "Publish it behind your HTTPS reverse proxy for $frontend_origin."
    note "Check the instance with: curl --fail $frontend_origin/api/health"
fi
