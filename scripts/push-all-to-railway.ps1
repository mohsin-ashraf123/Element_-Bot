# Sync local room cache + full DB to Railway (run after local messages update)
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== 1/4 Update bundled seed for next Docker deploy ==="
Copy-Item (Join-Path $root "backend\data\member_feed_cache.json") `
    (Join-Path $root "backend\seed\room_cache_seed.json") -Force -ErrorAction SilentlyContinue

Write-Host "=== 2/4 Sync room cache into local Postgres ==="
& (Join-Path $PSScriptRoot "sync-member-cache-to-db.ps1")

Write-Host ""
Write-Host "=== 3/4 Export local database ==="
& (Join-Path $PSScriptRoot "export-local-db.ps1")

Write-Host ""
Write-Host "=== 4/4 Import into Railway Postgres ==="
& (Join-Path $PSScriptRoot "import-railway-db.ps1") -DatabaseUrl $DatabaseUrl

Write-Host ""
Write-Host "Done. Redeploy pairflow-api on Railway (or wait for GitHub auto-deploy)."
