$ErrorActionPreference = "Stop"

$containerId = docker compose ps --quiet open-quiz-backend
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($containerId)) {
    & (Join-Path $PSScriptRoot "backup.ps1")
}

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose up --detach --build --remove-orphans
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose ps
