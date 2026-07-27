$ErrorActionPreference = "Stop"

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose up --detach --build --remove-orphans
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose ps
