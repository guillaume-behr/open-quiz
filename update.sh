#!/usr/bin/env sh

set -eu

git pull --ff-only
sudo docker compose up --detach --build --remove-orphans
sudo docker compose ps
