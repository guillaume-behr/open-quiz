#!/usr/bin/env sh

set -eu

if [ -n "$(sudo docker compose ps --quiet open-quiz-backend)" ]; then
    OPEN_QUIZ_DOCKER_SUDO=1 sh ./backup.sh
fi

git pull --ff-only
sudo docker compose up --detach --build --remove-orphans --wait --wait-timeout 120
sudo docker compose ps
