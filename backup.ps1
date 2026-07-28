$ErrorActionPreference = "Stop"

$containerId = docker compose ps --quiet open-quiz-backend
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($containerId)) {
    throw "The backend container must be running before a backup can be created."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDirectory = Join-Path $PSScriptRoot "backups"
$backupFile = Join-Path $backupDirectory "open-quiz-$timestamp.db"
$containerBackup = "/data/.open-quiz-backup-$timestamp.db"

New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null

$backupCode = @"
import sqlite3
source = sqlite3.connect("/data/open-quiz.db")
destination = sqlite3.connect("$containerBackup")
with destination:
    source.backup(destination)
result = destination.execute("PRAGMA quick_check").fetchone()[0]
source.close()
destination.close()
if result != "ok":
    raise RuntimeError(f"SQLite backup verification failed: {result}")
"@

try {
    docker compose exec --no-TTY open-quiz-backend /app/.venv/bin/python -c $backupCode
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    docker cp "${containerId}:${containerBackup}" $backupFile
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    docker compose exec --no-TTY open-quiz-backend /app/.venv/bin/python -c "from pathlib import Path; Path('$containerBackup').unlink(missing_ok=True)" 2>$null
}

Write-Host "Verified backup created at $backupFile"
