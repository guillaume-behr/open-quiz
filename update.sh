#!/usr/bin/env sh

set -eu

if [ -n "$(sudo docker compose ps --quiet open-quiz-backend)" ]; then
    sudo sh ./backup.sh
fi

git pull --ff-only
sudo docker compose up --detach --build --remove-orphans
sudo docker compose ps
