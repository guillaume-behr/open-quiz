#!/usr/bin/env sh

set -eu

git pull --ff-only

if docker info >/dev/null 2>&1; then
    compose() {
        docker compose "$@"
    }
elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    compose() {
        sudo docker compose "$@"
    }
else
    printf 'Error: Docker is not running or the current user cannot access it.\n' >&2
    exit 1
fi

compose config --quiet
compose up --detach --build --remove-orphans --wait --wait-timeout 120
compose ps
