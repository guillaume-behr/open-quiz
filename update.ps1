$ErrorActionPreference = "Stop"

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose up --detach --build --remove-orphans --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose ps
