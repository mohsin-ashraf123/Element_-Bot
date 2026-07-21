# One-shot: export local Postgres + import into Railway Postgres
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== 1/2 Export local database ==="
& (Join-Path $PSScriptRoot "export-local-db.ps1")

Write-Host ""
Write-Host "=== 2/2 Import into Railway ==="
& (Join-Path $PSScriptRoot "import-railway-db.ps1") -DatabaseUrl $DatabaseUrl

Write-Host ""
Write-Host "Done. In Railway dashboard:"
Write-Host "  pairflow-api -> Variables -> Add Reference -> pairflow-db -> DATABASE_URL"
Write-Host "  Then redeploy pairflow-api."
