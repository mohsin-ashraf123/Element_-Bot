#!/usr/bin/env pwsh
# Set Fly.io secrets from backend/.env (run after: flyctl auth login)
# Requires: free Neon Postgres — https://neon.tech (copy DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $PSScriptRoot ".." "backend" ".env"
if (-not (Test-Path $envFile)) { throw "Missing backend/.env" }

$vars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    $vars[$k.Trim()] = $v.Trim()
}

$frontend = "https://frontend-rho-pied-deqalmapg4.vercel.app"
$secrets = @(
    "APP_ENV=production",
    "ADMIN_USERNAME=$($vars.ADMIN_USERNAME)",
    "ADMIN_PASSWORD=$($vars.ADMIN_PASSWORD)",
    "SESSION_SECRET=$($vars.SESSION_SECRET)",
    "SECRETS_ENCRYPTION_KEY=$($vars.SECRETS_ENCRYPTION_KEY)",
    "DB_HOST=$($vars.DB_HOST)",
    "DB_PORT=$($vars.DB_PORT)",
    "DB_NAME=$($vars.DB_NAME)",
    "DB_USER=$($vars.DB_USER)",
    "DB_PASSWORD=$($vars.DB_PASSWORD)",
    "MATRIX_HOMESERVER_URL=$($vars.MATRIX_HOMESERVER_URL)",
    "MATRIX_BOT_USERNAME=$($vars.MATRIX_BOT_USERNAME)",
    "MATRIX_BOT_PASSWORD=$($vars.MATRIX_BOT_PASSWORD)",
    "MATRIX_ROOM_ID=$($vars.MATRIX_ROOM_ID)",
    "MATRIX_TASK_ROOM_ID=$($vars.MATRIX_TASK_ROOM_ID)",
    "MATRIX_DEVICE_ID=$($vars.MATRIX_DEVICE_ID)",
    "MATRIX_RECOVERY_KEY=$($vars.MATRIX_RECOVERY_KEY)",
    "MATRIX_PICKLE_KEY=$($vars.MATRIX_PICKLE_KEY)",
    "TIMEZONE=$($vars.TIMEZONE)",
    "DAILY_SEND_TIME=$($vars.DAILY_SEND_TIME)",
    "WORKING_DAYS=$($vars.WORKING_DAYS)",
    "TIMELINESS_CUTOFF=$($vars.TIMELINESS_CUTOFF)",
    "FRONTEND_URL=$frontend"
)

Push-Location (Join-Path $PSScriptRoot ".." "backend")
try {
    flyctl secrets set @secrets
    Write-Host "Secrets set. Run: flyctl deploy"
} finally {
    Pop-Location
}
