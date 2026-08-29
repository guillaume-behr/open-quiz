#Requires -Version 5.1
<#
.SYNOPSIS
    Update an Open Quiz deployment.
.DESCRIPTION
    Fetch the latest revision, rebuild the containers and wait until they
    report healthy.
.PARAMETER NoPull
    Rebuild and restart without fetching a new revision.
#>
[CmdletBinding()]
param(
    [switch]$NoPull
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$environmentFile = Join-Path $scriptDirectory "open-quiz-backend/.env"

# Brand purple is rgb(138, 79, 255), the --primary token of the interface.
$supportsColor = $Host.UI.SupportsVirtualTerminal -and -not $env:NO_COLOR
$purple = if ($supportsColor) { "$([char]27)[38;2;138;79;255m" } else { "" }
$bold = if ($supportsColor) { "$([char]27)[1m" } else { "" }
$dim = if ($supportsColor) { "$([char]27)[2m" } else { "" }
$reset = if ($supportsColor) { "$([char]27)[0m" } else { "" }

function Write-Banner {
    param([string]$Subtitle)
    $logo = @"
 ██████  ██████  ███████ ███    ██    ██████  ██    ██ ██ ███████
██    ██ ██   ██ ██      ████   ██   ██    ██ ██    ██ ██    ███
██    ██ ██████  █████   ██ ██  ██   ██    ██ ██    ██ ██   ███
██    ██ ██      ██      ██  ██ ██   ██ ▄▄ ██ ██    ██ ██  ███
 ██████  ██      ███████ ██   ████    ██████   ██████  ██ ███████
                                         ▀▀
"@
    Write-Host ""
    Write-Host "$purple$logo$reset"
    if ($Subtitle) { Write-Host "$dim$Subtitle$reset" }
    Write-Host ""
}

function Write-Step { param([string]$Message) Write-Host "$purple==>$reset $Message" }
function Write-Note { param([string]$Message) Write-Host "$dim    $Message$reset" }
function Write-Highlight { param([string]$Message) Write-Host "$bold$Message$reset" }

function Stop-WithError {
    param([string]$Message)
    [Console]::Error.WriteLine("Error: $Message")
    exit 1
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) { Stop-WithError $Message }
}

Write-Banner "Updating your deployment"

Set-Location $scriptDirectory

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithError "the 'docker' command is required"
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Docker is not running, or this user cannot reach it. Start Docker Desktop and try again."
}
if (-not (Test-Path -PathType Leaf $environmentFile)) {
    Stop-WithError "missing open-quiz-backend/.env; run 'sh ./install.sh' to create it"
}

if (-not $NoPull) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Stop-WithError "the 'git' command is required"
    }
    git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "this directory is not a Git clone; re-run with -NoPull, or clone the repository"
    }
    # A dirty tree makes --ff-only fail with a confusing message.
    if (git status --porcelain) {
        Stop-WithError "the working tree has local changes; commit, stash or discard them, or re-run with -NoPull"
    }

    $previousVersion = git describe --tags --always 2>$null
    if (-not $previousVersion) { $previousVersion = "unknown" }
    Write-Step "Fetching the latest revision"
    Invoke-Checked { git pull --ff-only } "git pull failed"
    $currentVersion = git describe --tags --always 2>$null
    if (-not $currentVersion) { $currentVersion = "unknown" }

    if ($previousVersion -eq $currentVersion) {
        Write-Note "Already up to date ($currentVersion)."
    }
    else {
        Write-Note "$previousVersion -> $currentVersion"
        Write-Highlight "Back up PostgreSQL before applying a version change."
        Write-Note "See docs/deployment.md for the pg_dump procedure."
    }
}
else {
    Write-Step "Skipping the revision fetch (-NoPull)"
}

Write-Step "Validating the Compose configuration"
Invoke-Checked { docker compose config --quiet } "the Compose configuration is invalid"

Write-Step "Building and starting the containers"
Invoke-Checked {
    docker compose up --detach --build --remove-orphans --wait --wait-timeout 120
} "the containers did not start"

Write-Step "Deployment status"
docker compose ps

$frontendOrigin = (Select-String -Path $environmentFile -Pattern '^FRONTEND_ORIGIN=(.+)$' |
    Select-Object -First 1).Matches.Groups[1].Value

Write-Host ""
Write-Highlight "Open Quiz is running on http://127.0.0.1:7800."
if ($frontendOrigin) {
    Write-Note "Publish it behind your HTTPS reverse proxy for $frontendOrigin."
    Write-Note "Check the instance with: curl --fail $frontendOrigin/api/health"
}
