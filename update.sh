#!/usr/bin/env sh

set -eu

git pull --ff-only
sudo docker compose up --detach --build --remove-orphans --wait --wait-timeout 120
sudo docker compose ps
