# Print env vars from backend/.env for pasting into Railway (pairflow-api -> Variables)
$ErrorActionPreference = "Stop"
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) "backend\.env"
if (-not (Test-Path $envFile)) { throw "Missing backend/.env" }

Write-Host "Copy these into Railway -> pairflow-api -> Variables"
Write-Host "(Skip DB_* - use DATABASE_URL reference from pairflow-db instead)"
Write-Host ""

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    $k = $k.Trim()
    if ($k -match '^DB_') { return }
    $val = $v.Trim()
    Write-Host ($k + '=' + $val)
}

Write-Host ""
Write-Host "Also add:"
Write-Host "  APP_ENV=production"
Write-Host "  FRONTEND_URL=https://frontend-rho-pied-deqalmapg4.vercel.app"
Write-Host "  (Ensure FRONTEND_URL is set on Railway for CORS)"
Write-Host "  MATRIX_E2EE_STORE_PATH=/app/data/matrix_store"
Write-Host "  DATABASE_URL=(Reference from pairflow-db service)"
