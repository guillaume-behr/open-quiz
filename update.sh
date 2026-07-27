#!/usr/bin/env sh

set -eu

git pull --ff-only
docker compose up --detach --build --remove-orphans
docker compose ps
